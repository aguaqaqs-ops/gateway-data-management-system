"""History compare accept transaction tests."""

from __future__ import annotations

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

import pytest

from gateway_backend.application.history.compare_bindings import (
    compute_accept_binding_fingerprint,
    deterministic_history_compare_ids,
)
from gateway_backend.application.history.compare import validate_history_compare_binding
from gateway_backend.application.history.contracts import (
    HISTORY_COMPARE_COMPARISON_CONTRACT_VERSION,
    HISTORY_COMPARE_JOB_CONTRACT_VERSION,
    HistoryCompareAcceptCommand,
    HistoryCompareAcceptanceRecord,
    HistoryCompareNodeBinding,
    HistoryNodeRef,
    HistoryNodeRefKind,
    PERMISSION_READ_PROJECT_HISTORY,
)
from gateway_backend.application.history.errors import (
    HistoryCompareIdempotencyConflict,
)
from gateway_backend.application.history.compare_jobs import history_compare_job_definitions
from gateway_backend.application.job_definitions import JobDefinitionRegistry
from gateway_backend.http.dependencies import OpenAdmissionGate
from gateway_backend.http.errors import ApiError
from gateway_backend.http.orchestration.history_compare import (
    HistoryCompareAcceptanceResult,
    accept_compare_operation,
)
from gateway_backend.infrastructure.control_db.database import ControlDbUnitOfWork
from gateway_backend.infrastructure.control_db.sqlite_history_compare import save_acceptance
from tests.support.baseline_fixtures import seed_provisioned_mapping_with_head
from tests.support.http_workspace_harness import BASELINE_HEAD
from tests.support.history_compare_job_harness import seed_archived_baseline_node
from tests.support.table_rules import _runtime_comparison_ruleset_digest
from tests.support.workspace_fixtures import make_identity

pytestmark = pytest.mark.unit

TS = datetime(2026, 9, 24, tzinfo=UTC)
HEAD_NODE = BASELINE_HEAD.business_baseline_node_id
HEAD_COMMIT = BASELINE_HEAD.business_baseline_commit_id
RUNTIME_RULESET_DIGEST = _runtime_comparison_ruleset_digest()


def _seed_scope(db_path: Path) -> None:
    seed_provisioned_mapping_with_head(db_path, baseline_head=BASELINE_HEAD)


def _accept_command(
    *,
    idempotency_key: str = "idem-1",
    nodes: tuple[HistoryNodeRef, ...] | None = None,
) -> HistoryCompareAcceptCommand:
    resolved_nodes = nodes or (
        HistoryNodeRef(HistoryNodeRefKind.BASELINE_NODE, HEAD_NODE),
        HistoryNodeRef(HistoryNodeRefKind.BASELINE_NODE, HEAD_NODE),
    )
    return HistoryCompareAcceptCommand(
        context=make_identity(permissions=frozenset({PERMISSION_READ_PROJECT_HISTORY})),
        idempotency_key=idempotency_key,
        node_refs=resolved_nodes,
    )


def test_deterministic_ids_are_stable_for_same_input() -> None:
    kwargs = {
        "gateway_device_external_key": "device-1",
        "business_project_id": "project-1",
        "idempotency_key": "stable-key",
    }
    first = deterministic_history_compare_ids(**kwargs)
    second = deterministic_history_compare_ids(**kwargs)
    assert first == second


def test_deterministic_ids_use_named_key_preimage() -> None:
    first = deterministic_history_compare_ids(
        gateway_device_external_key="dev:a",
        business_project_id="p",
        idempotency_key="k",
    )
    second = deterministic_history_compare_ids(
        gateway_device_external_key="dev",
        business_project_id="a:p",
        idempotency_key="k",
    )
    third = deterministic_history_compare_ids(
        gateway_device_external_key="dev:a",
        business_project_id="p",
        idempotency_key="k2",
    )
    assert first != second
    assert first != third
    assert first[0].startswith("op-")
    assert first[1].startswith("hca-")


def test_accept_binding_fingerprint_freezes_comparison_ruleset_digest() -> None:
    from gateway_backend.application.history.compare_bindings import _accept_binding_payload

    nodes = (
        HistoryCompareNodeBinding(HistoryNodeRefKind.BASELINE_NODE, HEAD_NODE, HEAD_COMMIT),
        HistoryCompareNodeBinding(HistoryNodeRefKind.BASELINE_NODE, HEAD_NODE, HEAD_COMMIT),
    )
    fingerprint = compute_accept_binding_fingerprint(
        gateway_device_external_key="device-1",
        business_project_id="project-1",
        repository_id="repo-1",
        nodes=nodes,
        comparison_ruleset_digest=RUNTIME_RULESET_DIGEST,
        comparison_contract_version=HISTORY_COMPARE_COMPARISON_CONTRACT_VERSION,
        view_kind="HISTORY",
    )
    payload = _accept_binding_payload(
        gateway_device_external_key="device-1",
        business_project_id="project-1",
        repository_id="repo-1",
        nodes=nodes,
        comparison_ruleset_digest=RUNTIME_RULESET_DIGEST,
        comparison_contract_version=HISTORY_COMPARE_COMPARISON_CONTRACT_VERSION,
        history_job_contract_version=HISTORY_COMPARE_JOB_CONTRACT_VERSION,
        view_kind="HISTORY",
        pair_count=1,
    )
    assert set(payload) == {
        "gateway_device_external_key",
        "business_project_id",
        "repository_id",
        "nodes",
        "comparison_ruleset_digest",
        "comparison_contract_version",
        "history_job_contract_version",
        "view_kind",
        "pair_count",
    }
    with_ruleset_a = compute_accept_binding_fingerprint(
        gateway_device_external_key="device-1",
        business_project_id="project-1",
        repository_id="repo-1",
        nodes=nodes,
        comparison_ruleset_digest="sha256:ruleset-a",
        comparison_contract_version=HISTORY_COMPARE_COMPARISON_CONTRACT_VERSION,
        view_kind="HISTORY",
        pair_count=1,
    )
    with_ruleset_b = compute_accept_binding_fingerprint(
        gateway_device_external_key="device-1",
        business_project_id="project-1",
        repository_id="repo-1",
        nodes=nodes,
        comparison_ruleset_digest="sha256:ruleset-b",
        comparison_contract_version=HISTORY_COMPARE_COMPARISON_CONTRACT_VERSION,
        view_kind="HISTORY",
        pair_count=1,
    )
    assert fingerprint.startswith("sha256:")
    assert with_ruleset_a != fingerprint
    assert with_ruleset_b != fingerprint
    assert with_ruleset_a != with_ruleset_b
    assert fingerprint != compute_accept_binding_fingerprint(
        gateway_device_external_key="device-1",
        business_project_id="project-1",
        repository_id="repo-1",
        nodes=nodes,
        comparison_ruleset_digest=RUNTIME_RULESET_DIGEST,
        history_job_contract_version="different-history-version",
    )
    assert fingerprint != compute_accept_binding_fingerprint(
        gateway_device_external_key="device-1",
        business_project_id="project-1",
        repository_id="repo-1",
        nodes=nodes,
        comparison_ruleset_digest=RUNTIME_RULESET_DIGEST,
        comparison_contract_version="different-comparison-version",
    )
    assert fingerprint == compute_accept_binding_fingerprint(
        gateway_device_external_key="device-1",
        business_project_id="project-1",
        repository_id="repo-1",
        nodes=nodes,
        comparison_ruleset_digest=RUNTIME_RULESET_DIGEST,
        comparison_contract_version=HISTORY_COMPARE_COMPARISON_CONTRACT_VERSION,
        view_kind="HISTORY",
    )


def test_acceptance_timestamp_preserves_microseconds() -> None:
    from datetime import UTC, datetime

    from gateway_backend.infrastructure.control_db.sqlite_history_compare import (
        _datetime_to_epoch_us,
        _epoch_us_to_datetime,
    )

    timestamp = datetime(2026, 11, 15, 12, 0, 0, 987654, tzinfo=UTC)
    assert _epoch_us_to_datetime(_datetime_to_epoch_us(timestamp)) == timestamp


def test_idempotent_replay_returns_existing_acceptance(db_path: Path) -> None:
    _seed_scope(db_path)
    nodes = (
        HistoryCompareNodeBinding(HistoryNodeRefKind.BASELINE_NODE, HEAD_NODE, HEAD_COMMIT),
        HistoryCompareNodeBinding(HistoryNodeRefKind.BASELINE_NODE, HEAD_NODE, HEAD_COMMIT),
    )
    operation_id, acceptance_id = deterministic_history_compare_ids(
        gateway_device_external_key="device-1",
        business_project_id="project-1",
        idempotency_key="idem-replay",
    )
    with ControlDbUnitOfWork(db_path) as unit_of_work:
        save_acceptance(
            unit_of_work.connection,
            HistoryCompareAcceptanceRecord(
                acceptance_id=acceptance_id,
                gateway_device_external_key="device-1",
                business_project_id="project-1",
                repository_id="repo-1",
                idempotency_key="idem-replay",
                request_fingerprint=compute_accept_binding_fingerprint(
                    gateway_device_external_key="device-1",
                    business_project_id="project-1",
                    repository_id="repo-1",
                    nodes=nodes,
                    comparison_ruleset_digest=RUNTIME_RULESET_DIGEST,
                ),
                comparison_ruleset_digest=RUNTIME_RULESET_DIGEST,
                nodes=nodes,
                operation_id=operation_id,
                created_at=TS,
            ),
        )
        result = validate_history_compare_binding(
            command=_accept_command(idempotency_key="idem-replay"),
            unit_of_work=unit_of_work,
            comparison_ruleset_digest=RUNTIME_RULESET_DIGEST,
        )
    assert result.replay is True
    assert result.operation_id == operation_id


@pytest.mark.parametrize(
    "old_ruleset,old_job",
    [
        ("sha256:old-ruleset", HISTORY_COMPARE_JOB_CONTRACT_VERSION),
        (RUNTIME_RULESET_DIGEST, "backend-vnext/history-compare/v4"),
    ],
)
def test_semantic_drift_replay_raises_idempotency_conflict(
    db_path: Path,
    old_ruleset: str,
    old_job: str,
) -> None:
    _seed_scope(db_path)
    nodes = (
        HistoryCompareNodeBinding(HistoryNodeRefKind.BASELINE_NODE, HEAD_NODE, HEAD_COMMIT),
        HistoryCompareNodeBinding(HistoryNodeRefKind.BASELINE_NODE, HEAD_NODE, HEAD_COMMIT),
    )
    operation_id, acceptance_id = deterministic_history_compare_ids(
        gateway_device_external_key="device-1",
        business_project_id="project-1",
        idempotency_key="idem-ruleset",
    )
    with ControlDbUnitOfWork(db_path) as unit_of_work:
        save_acceptance(
            unit_of_work.connection,
            HistoryCompareAcceptanceRecord(
                acceptance_id=acceptance_id,
                gateway_device_external_key="device-1",
                business_project_id="project-1",
                repository_id="repo-1",
                idempotency_key="idem-ruleset",
                request_fingerprint=compute_accept_binding_fingerprint(
                    gateway_device_external_key="device-1",
                    business_project_id="project-1",
                    repository_id="repo-1",
                    nodes=nodes,
                    comparison_ruleset_digest=old_ruleset,
                    comparison_contract_version=HISTORY_COMPARE_COMPARISON_CONTRACT_VERSION,
                    history_job_contract_version=old_job,
                    view_kind="HISTORY",
                ),
                comparison_ruleset_digest=old_ruleset,
                nodes=nodes,
                operation_id=operation_id,
                created_at=TS,
            ),
        )
        with pytest.raises(HistoryCompareIdempotencyConflict):
            validate_history_compare_binding(
                command=_accept_command(idempotency_key="idem-ruleset"),
                unit_of_work=unit_of_work,
                comparison_ruleset_digest=RUNTIME_RULESET_DIGEST,
            )


def test_idempotency_conflict_on_changed_nodes(db_path: Path) -> None:
    _seed_scope(db_path)
    seed_archived_baseline_node(
        db_path,
        node_id="bn-other",
        commit_id="commit-b",
        created_at_us=2,
    )
    nodes = (
        HistoryCompareNodeBinding(HistoryNodeRefKind.BASELINE_NODE, HEAD_NODE, HEAD_COMMIT),
        HistoryCompareNodeBinding(HistoryNodeRefKind.BASELINE_NODE, HEAD_NODE, HEAD_COMMIT),
    )
    operation_id, acceptance_id = deterministic_history_compare_ids(
        gateway_device_external_key="device-1",
        business_project_id="project-1",
        idempotency_key="idem-conflict",
    )
    with ControlDbUnitOfWork(db_path) as unit_of_work:
        save_acceptance(
            unit_of_work.connection,
            HistoryCompareAcceptanceRecord(
                acceptance_id=acceptance_id,
                gateway_device_external_key="device-1",
                business_project_id="project-1",
                repository_id="repo-1",
                idempotency_key="idem-conflict",
                request_fingerprint=compute_accept_binding_fingerprint(
                    gateway_device_external_key="device-1",
                    business_project_id="project-1",
                    repository_id="repo-1",
                    nodes=nodes,
                    comparison_ruleset_digest=RUNTIME_RULESET_DIGEST,
                ),
                comparison_ruleset_digest=RUNTIME_RULESET_DIGEST,
                nodes=nodes,
                operation_id=operation_id,
                created_at=TS,
            ),
        )
        with pytest.raises(HistoryCompareIdempotencyConflict):
            validate_history_compare_binding(
                command=_accept_command(
                    idempotency_key="idem-conflict",
                    nodes=(
                        HistoryNodeRef(HistoryNodeRefKind.BASELINE_NODE, HEAD_NODE),
                        HistoryNodeRef(HistoryNodeRefKind.BASELINE_NODE, "bn-other"),
                    ),
                ),
                unit_of_work=unit_of_work,
                comparison_ruleset_digest=RUNTIME_RULESET_DIGEST,
            )


def _history_accept_row_counts(db_path: Path) -> tuple[int, int, int]:
    with sqlite3.connect(db_path) as connection:
        acceptance_count = connection.execute(
            "SELECT COUNT(*) FROM history_compare_acceptance_records"
        ).fetchone()[0]
        operation_count = connection.execute("SELECT COUNT(*) FROM operation_records").fetchone()[0]
        step_count = connection.execute("SELECT COUNT(*) FROM step_records").fetchone()[0]
    return acceptance_count, operation_count, step_count


def test_concurrent_accept_with_same_idempotency_key_has_single_winner(db_path: Path) -> None:
    _seed_scope(db_path)
    seed_archived_baseline_node(
        db_path,
        node_id="bn-concurrent-b",
        commit_id="commit-concurrent-b",
        created_at_us=2,
    )
    job_registry = JobDefinitionRegistry.build(history_compare_job_definitions())
    command = _accept_command(
        idempotency_key="idem-concurrent",
        nodes=(
            HistoryNodeRef(HistoryNodeRefKind.BASELINE_NODE, HEAD_NODE),
            HistoryNodeRef(HistoryNodeRefKind.BASELINE_NODE, "bn-concurrent-b"),
        ),
    )

    def attempt() -> object:
        return accept_compare_operation(
            command=command,
            unit_of_work_factory=lambda *, read_only=False: ControlDbUnitOfWork(
                db_path, read_only=read_only
            ),
            job_registry=job_registry,
            admission_gate=OpenAdmissionGate(),
            comparison_ruleset_digest=RUNTIME_RULESET_DIGEST,
            now=TS,
        )

    outcomes: list[object] = []
    errors: list[BaseException] = []

    def runner() -> None:
        try:
            outcomes.append(attempt())
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(runner), executor.submit(runner)]
        for future in futures:
            future.result()

    assert len(outcomes) + len(errors) == 2
    fresh = [item for item in outcomes if not getattr(item, "replay", False)]
    replays = [item for item in outcomes if getattr(item, "replay", False)]
    idempotency_conflicts = [
        exc for exc in errors if isinstance(exc, ApiError) and exc.code == "IDEMPOTENCY_CONFLICT"
    ]
    other_errors = [exc for exc in errors if exc not in idempotency_conflicts]
    assert len(fresh) == 1
    assert len(replays) + len(idempotency_conflicts) == 1
    assert not other_errors
    for exc in idempotency_conflicts:
        assert exc.status_code == 409
    assert _history_accept_row_counts(db_path)[0] == 1


def test_replay_requires_current_permission(db_path: Path) -> None:
    from tests.support.baseline_fixtures import upsert_provisioned_mapping_row

    _seed_scope(db_path)
    seed_archived_baseline_node(
        db_path,
        node_id="bn-replay-b",
        commit_id="commit-replay-b",
        created_at_us=2,
    )
    job_registry = JobDefinitionRegistry.build(history_compare_job_definitions())
    nodes = (
        HistoryNodeRef(HistoryNodeRefKind.BASELINE_NODE, HEAD_NODE),
        HistoryNodeRef(HistoryNodeRefKind.BASELINE_NODE, "bn-replay-b"),
    )
    accept_compare_operation(
        command=_accept_command(idempotency_key="idem-replay-auth", nodes=nodes),
        unit_of_work_factory=lambda *, read_only=False: ControlDbUnitOfWork(
            db_path, read_only=read_only
        ),
        job_registry=job_registry,
        admission_gate=OpenAdmissionGate(),
        comparison_ruleset_digest=RUNTIME_RULESET_DIGEST,
        now=TS,
    )
    denied = make_identity(permissions=frozenset({"workspace_read"}))
    with pytest.raises(ApiError) as exc_info:
        accept_compare_operation(
            command=HistoryCompareAcceptCommand(
                context=denied,
                idempotency_key="idem-replay-auth",
                node_refs=nodes,
            ),
            unit_of_work_factory=lambda *, read_only=False: ControlDbUnitOfWork(
                db_path, read_only=read_only
            ),
            job_registry=job_registry,
            admission_gate=OpenAdmissionGate(),
            comparison_ruleset_digest=RUNTIME_RULESET_DIGEST,
            now=TS,
        )
    assert exc_info.value.code == "SCOPE_FORBIDDEN"

    upsert_provisioned_mapping_row(db_path, repository_id="repo-2", baseline_head=BASELINE_HEAD)
    with pytest.raises(ApiError) as first_rebind_exc:
        accept_compare_operation(
            command=_accept_command(idempotency_key="idem-replay-auth", nodes=nodes),
            unit_of_work_factory=lambda *, read_only=False: ControlDbUnitOfWork(
                db_path, read_only=read_only
            ),
            job_registry=job_registry,
            admission_gate=OpenAdmissionGate(),
            comparison_ruleset_digest=RUNTIME_RULESET_DIGEST,
            now=TS,
        )
    with pytest.raises(ApiError) as second_rebind_exc:
        accept_compare_operation(
            command=_accept_command(idempotency_key="idem-replay-auth", nodes=nodes),
            unit_of_work_factory=lambda *, read_only=False: ControlDbUnitOfWork(
                db_path, read_only=read_only
            ),
            job_registry=job_registry,
            admission_gate=OpenAdmissionGate(),
            comparison_ruleset_digest=RUNTIME_RULESET_DIGEST,
            now=TS,
        )
    assert first_rebind_exc.value.status_code == 409
    assert first_rebind_exc.value.code == "IDEMPOTENCY_CONFLICT"
    assert second_rebind_exc.value.status_code == 409
    assert second_rebind_exc.value.code == "IDEMPOTENCY_CONFLICT"


def test_distinct_keys_reuse_active_operation_and_alias_replays(db_path: Path) -> None:
    from gateway_backend.application.history.compare_jobs import (
        HISTORY_COMPARE_STEP_MATERIALIZE,
        history_compare_step_id,
    )

    _seed_scope(db_path)
    seed_archived_baseline_node(
        db_path,
        node_id="bn-distinct-b",
        commit_id="commit-distinct-b",
        created_at_us=2,
    )
    job_registry = JobDefinitionRegistry.build(history_compare_job_definitions())
    nodes = (
        HistoryNodeRef(HistoryNodeRefKind.BASELINE_NODE, HEAD_NODE),
        HistoryNodeRef(HistoryNodeRefKind.BASELINE_NODE, "bn-distinct-b"),
    )
    first = accept_compare_operation(
        command=_accept_command(idempotency_key="idem-distinct-a", nodes=nodes),
        unit_of_work_factory=lambda *, read_only=False: ControlDbUnitOfWork(
            db_path, read_only=read_only
        ),
        job_registry=job_registry,
        admission_gate=OpenAdmissionGate(),
        comparison_ruleset_digest=RUNTIME_RULESET_DIGEST,
        now=TS,
    )
    second = accept_compare_operation(
        command=_accept_command(idempotency_key="idem-distinct-b", nodes=nodes),
        unit_of_work_factory=lambda *, read_only=False: ControlDbUnitOfWork(
            db_path, read_only=read_only
        ),
        job_registry=job_registry,
        admission_gate=OpenAdmissionGate(),
        comparison_ruleset_digest=RUNTIME_RULESET_DIGEST,
        now=TS,
    )
    assert first.replay is False
    assert second.replay is True
    assert first.response.operation_id == second.response.operation_id
    assert _history_accept_row_counts(db_path) == (1, 1, 1)
    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        acceptance = unit_of_work.history_compare.find_acceptance_by_idempotency(
            gateway_device_external_key="device-1",
            business_project_id="project-1",
            idempotency_key="idem-distinct-b",
        )
        assert acceptance is not None
        assert acceptance.operation_id == first.response.operation_id
        assert unit_of_work.history_compare.count_aliases(acceptance.operation_id) == 1
        step = unit_of_work.operations.get_step(
            history_compare_step_id(acceptance.operation_id, HISTORY_COMPARE_STEP_MATERIALIZE)
        )
        assert step.step_name == HISTORY_COMPARE_STEP_MATERIALIZE
    replay = accept_compare_operation(
        command=_accept_command(idempotency_key="idem-distinct-b", nodes=nodes),
        unit_of_work_factory=lambda *, read_only=False: ControlDbUnitOfWork(
            db_path, read_only=read_only
        ),
        job_registry=job_registry,
        admission_gate=OpenAdmissionGate(),
        comparison_ruleset_digest=RUNTIME_RULESET_DIGEST,
        now=TS,
    )
    assert replay.replay and replay.response.operation_id == first.response.operation_id


@pytest.mark.parametrize("fingerprint_matches_current", (False, True))
def test_new_history_key_does_not_reuse_old_successful_job(
    db_path: Path,
    fingerprint_matches_current: bool,
) -> None:
    _seed_scope(db_path)
    registry = JobDefinitionRegistry.build(history_compare_job_definitions())
    now = datetime.now(UTC)

    def accept(key: str) -> HistoryCompareAcceptanceResult:
        return accept_compare_operation(
            command=_accept_command(idempotency_key=key),
            unit_of_work_factory=lambda *, read_only=False: ControlDbUnitOfWork(
                db_path, read_only=read_only
            ),
            job_registry=registry,
            admission_gate=OpenAdmissionGate(),
            comparison_ruleset_digest=RUNTIME_RULESET_DIGEST,
            now=now,
        )

    old = accept("old-job-key")
    old_id = old.response.operation_id
    bindings = (
        HistoryCompareNodeBinding(HistoryNodeRefKind.BASELINE_NODE, HEAD_NODE, HEAD_COMMIT),
        HistoryCompareNodeBinding(HistoryNodeRefKind.BASELINE_NODE, HEAD_NODE, HEAD_COMMIT),
    )
    old_fingerprint = compute_accept_binding_fingerprint(
        gateway_device_external_key="device-1",
        business_project_id="project-1",
        repository_id="repo-1",
        nodes=bindings,
        comparison_ruleset_digest=RUNTIME_RULESET_DIGEST,
        history_job_contract_version="backend-vnext/history-compare/v3",
    )
    with ControlDbUnitOfWork(db_path) as uow:
        uow.connection.execute(
            "UPDATE operation_records SET status='SUCCEEDED', completed_at_us=created_at_us, "
            "job_contract_version=? WHERE operation_id=?",
            ("backend-vnext/history-compare/v3", old_id),
        )
        if not fingerprint_matches_current:
            uow.connection.execute(
                "UPDATE history_compare_acceptance_records SET request_fingerprint=? WHERE operation_id=?",
                (old_fingerprint, old_id),
            )
        else:
            # A matching fingerprint must still pass the operation's own version check.
            candidates = uow.history_compare.find_candidates(
                gateway_device_external_key="device-1",
                business_project_id="project-1",
                request_fingerprint=compute_accept_binding_fingerprint(
                    gateway_device_external_key="device-1",
                    business_project_id="project-1",
                    repository_id="repo-1",
                    nodes=bindings,
                    comparison_ruleset_digest=RUNTIME_RULESET_DIGEST,
                ),
                now=uow.transaction_now,
            )
            assert any(candidate.operation_id == old_id for candidate in candidates)

    fresh = accept("new-job-key")
    assert fresh.replay is False
    assert fresh.response.operation_id != old_id
    with ControlDbUnitOfWork(db_path, read_only=True) as uow:
        old_operation = uow.operations.get_operation(old_id)
        assert old_operation.job_contract_version == "backend-vnext/history-compare/v3"
        assert old_operation.status.value == "SUCCEEDED"
        assert uow.history_compare.count_aliases(old_id) == 0


def test_scope_limit_allows_existing_reuse_before_rejecting_new_input(db_path: Path) -> None:
    _seed_scope(db_path)
    seed_archived_baseline_node(
        db_path, node_id="bn-limit-b", commit_id="commit-limit-b", created_at_us=2
    )
    registry = JobDefinitionRegistry.build(history_compare_job_definitions())
    first_nodes = (
        HistoryNodeRef(HistoryNodeRefKind.BASELINE_NODE, HEAD_NODE),
        HistoryNodeRef(HistoryNodeRefKind.BASELINE_NODE, "bn-limit-b"),
    )

    def accept(key: str, nodes: tuple[HistoryNodeRef, ...]) -> HistoryCompareAcceptanceResult:
        return accept_compare_operation(
            command=_accept_command(idempotency_key=key, nodes=nodes),
            unit_of_work_factory=lambda *, read_only=False: ControlDbUnitOfWork(
                db_path, read_only=read_only
            ),
            job_registry=registry,
            admission_gate=OpenAdmissionGate(),
            comparison_ruleset_digest=RUNTIME_RULESET_DIGEST,
            now=TS,
        )

    first = accept("limit-first", first_nodes)
    accept("limit-second", tuple(reversed(first_nodes)))
    assert accept("limit-alias", first_nodes).response.operation_id == first.response.operation_id
    with pytest.raises(ApiError) as error:
        accept("limit-third", (first_nodes[0], first_nodes[0]))
    assert error.value.code == "HISTORY_COMPARE_SCOPE_LIMIT"
    assert error.value.status_code == 409


@pytest.mark.serial
def test_concurrent_distinct_keys_share_one_active_history_operation(db_path: Path) -> None:
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    _seed_scope(db_path)
    registry = JobDefinitionRegistry.build(history_compare_job_definitions())
    ready = Barrier(2)

    def accept(key: str) -> HistoryCompareAcceptanceResult:
        ready.wait()
        return accept_compare_operation(
            command=_accept_command(idempotency_key=key),
            unit_of_work_factory=lambda *, read_only=False: ControlDbUnitOfWork(
                db_path, read_only=read_only
            ),
            job_registry=registry,
            admission_gate=OpenAdmissionGate(),
            comparison_ruleset_digest=RUNTIME_RULESET_DIGEST,
            now=TS,
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(accept, ("concurrent-a", "concurrent-b")))
    assert outcomes[0].response.operation_id == outcomes[1].response.operation_id
    assert sorted(item.replay for item in outcomes) == [False, True]
    assert _history_accept_row_counts(db_path) == (1, 1, 1)


def test_global_queue_limit_counts_other_job_kinds_but_allows_replay(db_path: Path) -> None:
    _seed_scope(db_path)
    seed_archived_baseline_node(
        db_path, node_id="bn-queue-b", commit_id="commit-queue-b", created_at_us=2
    )
    registry = JobDefinitionRegistry.build(history_compare_job_definitions())
    first_nodes = (
        HistoryNodeRef(HistoryNodeRefKind.BASELINE_NODE, HEAD_NODE),
        HistoryNodeRef(HistoryNodeRefKind.BASELINE_NODE, "bn-queue-b"),
    )

    def accept(key: str, nodes: tuple[HistoryNodeRef, ...]) -> HistoryCompareAcceptanceResult:
        return accept_compare_operation(
            command=_accept_command(idempotency_key=key, nodes=nodes),
            unit_of_work_factory=lambda *, read_only=False: ControlDbUnitOfWork(
                db_path, read_only=read_only
            ),
            job_registry=registry,
            admission_gate=OpenAdmissionGate(),
            comparison_ruleset_digest=RUNTIME_RULESET_DIGEST,
            now=TS,
            operation_queue_limit=1,
        )

    first = accept("queue-first", first_nodes)
    assert accept("queue-first", first_nodes).response.operation_id == first.response.operation_id
    with ControlDbUnitOfWork(db_path) as uow:
        uow.connection.execute(
            "UPDATE operation_records SET job_kind = 'another-job-kind' WHERE operation_id = ?",
            (first.response.operation_id,),
        )
    with pytest.raises(ApiError) as error:
        accept("queue-second", tuple(reversed(first_nodes)))
    assert error.value.code == "OPERATION_QUEUE_FULL"
    assert error.value.status_code == 429
