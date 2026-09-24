"""History compare integrity acknowledgement tests."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from gateway_backend.application.history.contracts import (
    HISTORY_INTEGRITY_FAILURE_CLASS,
    HISTORY_INTEGRITY_RECOMMENDED_ACTION,
    HistoryCompareIntegrityRecord,
    IntegrityAcknowledgementStatus,
)
from gateway_backend.http.orchestration.history_integrity import acknowledge_integrity_incident
from gateway_backend.infrastructure.control_db.database import ControlDbUnitOfWork
from gateway_backend.application.history.compare_jobs import HISTORY_COMPARE_MATERIALIZE_HANDLER
from gateway_backend.operations import OperationStatus
from tests.support.http_workspace_harness import BASELINE_HEAD
from tests.support.history_compare_job_harness import (
    build_history_compare_harness,
    history_compare_provider,
    insert_history_compare_operation,
    run_through_step,
)
from tests.support.repository_ref_materialization import FakeRepositoryTableAccessProvider
from gateway_backend.capabilities.snapshot_materialization._digest import (
    raw_content_digest_of,
    row_content_hash,
)
from gateway_backend.capabilities.snapshot_materialization.scalar_encoding import (
    encode_repository_row,
    map_repository_column,
)
from gateway_shared_kernel import raw_blob_digest

from tests.support.repository_ref_materialization import (
    catalog_table,
    hidden_summary_for,
    int_id_column,
    make_catalog,
)

pytestmark = pytest.mark.unit

TS = datetime(2026, 9, 24, tzinfo=UTC)


def test_acknowledge_integrity_incident_updates_record(tmp_path: Path) -> None:
    harness = build_history_compare_harness(
        tmp_path,
        mutate_snapshot_digest_for=frozenset({BASELINE_HEAD.business_baseline_commit_id}),
        idempotency_key="history-compare-ack",
    )
    insert_history_compare_operation(harness)
    run_through_step(harness, HISTORY_COMPARE_MATERIALIZE_HANDLER)

    response = acknowledge_integrity_incident(
        operation_id=harness.operation_id,
        acknowledgement_status=IntegrityAcknowledgementStatus.ACKNOWLEDGED.value,
        resolution_reference="ticket-123",
        unit_of_work_factory=lambda *, read_only=False: ControlDbUnitOfWork(
            harness.db_path,
            read_only=read_only,
        ),
        now=TS,
    )
    assert response.acknowledgement_status == IntegrityAcknowledgementStatus.ACKNOWLEDGED.value
    assert response.resolution_reference == "ticket-123"

    with ControlDbUnitOfWork(harness.db_path, read_only=True) as unit_of_work:
        updated = unit_of_work.history_compare.get_integrity_by_operation_id(harness.operation_id)
    assert updated is not None
    assert updated.acknowledgement_status is IntegrityAcknowledgementStatus.ACKNOWLEDGED
    assert updated.resolution_reference == "ticket-123"


def test_row_digest_mismatch_publishes_integrity_incident(tmp_path: Path) -> None:
    harness = build_history_compare_harness(
        tmp_path,
        mutate_raw_digest_for=frozenset({BASELINE_HEAD.business_baseline_commit_id}),
        idempotency_key="history-compare-row-digest",
    )
    table = catalog_table("t", (int_id_column(),))
    rows = {"t": ((1,),)}
    catalog = make_catalog((table,), commit=BASELINE_HEAD.business_baseline_commit_id)
    mapped = tuple(map_repository_column(column) for column in table.columns)
    source_columns = tuple(item.source for item in mapped)
    encoded = encode_repository_row(table.columns, (1,), table="t").cells
    observed_digest = raw_content_digest_of((row_content_hash(source_columns, encoded),))
    hidden = hidden_summary_for(catalog, rows, mutate_raw_digest_table="t")
    expected_digest = hidden.tables[0].raw_content_digest
    assert expected_digest is not None
    assert observed_digest != expected_digest

    insert_history_compare_operation(harness)
    run_through_step(harness, HISTORY_COMPARE_MATERIALIZE_HANDLER)

    with ControlDbUnitOfWork(harness.db_path, read_only=True) as unit_of_work:
        operation = unit_of_work.operations.get_operation(harness.operation_id)
        incident = unit_of_work.history_compare.get_integrity_by_operation_id(harness.operation_id)
    assert operation.status is OperationStatus.FAILED
    assert incident is not None
    assert incident.expected_digest == expected_digest.value
    assert incident.observed_digest == observed_digest.value
    assert operation.ready_closure_ref is None
    assert incident.first_seen_at <= incident.last_seen_at


INTEGRITY_SCENARIO_CASES = (
    "content_stable",
    "content_drifting",
    "structural_no_content_pair",
)

_ROWS_A: dict[str, tuple[tuple[int,], ...]] = {"t": ((1,),)}
_ROWS_B: dict[str, tuple[tuple[int,], ...]] = {"t": ((2,),)}
_ROWS_C: dict[str, tuple[tuple[int,], ...]] = {"t": ((3,),)}


def _content_digest_oracle(
    declared_rows: dict[str, tuple[tuple[int,], ...]],
    session_rows: dict[str, tuple[tuple[int,], ...]],
    *,
    commit_id: str,
) -> tuple[str, str]:
    table = catalog_table("t", (int_id_column(),))
    catalog = make_catalog((table,), commit=commit_id)
    hidden = hidden_summary_for(catalog, declared_rows)
    expected_digest = hidden.tables[0].raw_content_digest
    assert expected_digest is not None
    mapped = tuple(map_repository_column(column) for column in table.columns)
    source_columns = tuple(item.source for item in mapped)
    encoded = tuple(
        encode_repository_row(table.columns, tuple(row), table="t").cells
        for row in session_rows["t"]
    )
    row_hashes = tuple(row_content_hash(source_columns, row) for row in encoded)
    observed_digest = raw_content_digest_of(row_hashes)
    return expected_digest.value, observed_digest.value


def _structural_digest_oracle() -> tuple[str, str]:
    return (
        raw_blob_digest(b"catalog-table:t").value,
        raw_blob_digest(b"catalog-table:missing").value,
    )


def _provider_for_integrity_scenario(
    scenario: str,
    commit_id: str,
) -> FakeRepositoryTableAccessProvider:
    from tests.support.history_compare_job_harness import history_compare_provider

    if scenario == "content_stable":
        return history_compare_provider(
            commit_id=commit_id,
            declared_rows=_ROWS_A,
            per_read_rows=(_ROWS_B, _ROWS_B),
        )
    if scenario == "content_drifting":
        return history_compare_provider(
            commit_id=commit_id,
            declared_rows=_ROWS_A,
            per_read_rows=(_ROWS_B, _ROWS_C),
        )
    if scenario == "structural_no_content_pair":
        return history_compare_provider(
            commit_id=commit_id,
            declared_rows=_ROWS_A,
            catalog_without=("t",),
        )
    if scenario == "structural_second_read_recovers":
        return history_compare_provider(
            commit_id=commit_id,
            declared_rows=_ROWS_A,
            per_read_catalog_without=(("t",), ()),
            per_read_hidden_catalog_without=((), ("t",)),
        )
    raise ValueError(f"unknown scenario: {scenario}")


def _expected_incident_digests(
    scenario: str,
    *,
    commit_id: str,
) -> tuple[str, str, tuple[str, ...]]:
    if scenario == "structural_no_content_pair":
        expected_digest, observed_digest = _structural_digest_oracle()
        return expected_digest, observed_digest, ("t",)
    expected_digest, observed_digest = _content_digest_oracle(_ROWS_A, _ROWS_B, commit_id=commit_id)
    return expected_digest, observed_digest, ("t",)


@pytest.mark.parametrize("scenario", INTEGRITY_SCENARIO_CASES)
def test_integrity_scenario_parameter_table(tmp_path: Path, scenario: str) -> None:
    commit_id = BASELINE_HEAD.business_baseline_commit_id
    commit_b = "commit-b"
    provider = _provider_for_integrity_scenario(scenario, commit_id)
    expected_digest, observed_digest, affected_tables = _expected_incident_digests(
        scenario,
        commit_id=commit_id,
    )
    harness = build_history_compare_harness(
        tmp_path,
        custom_providers={
            commit_id: provider,
            commit_b: history_compare_provider(commit_id=commit_b),
        },
        idempotency_key=f"history-compare-f5-{scenario}",
    )
    insert_history_compare_operation(harness)
    run_through_step(harness, HISTORY_COMPARE_MATERIALIZE_HANDLER)

    with ControlDbUnitOfWork(harness.db_path, read_only=True) as unit_of_work:
        operation = unit_of_work.operations.get_operation(harness.operation_id)
        incident = unit_of_work.history_compare.get_integrity_by_operation_id(harness.operation_id)
    assert operation.status is OperationStatus.FAILED
    assert incident is not None
    assert incident.failure_class == HISTORY_INTEGRITY_FAILURE_CLASS
    assert incident.commit_refs == ({"commit_id": commit_id},)
    assert incident.recommended_action == HISTORY_INTEGRITY_RECOMMENDED_ACTION
    assert incident.expected_digest == expected_digest
    assert incident.observed_digest == observed_digest
    assert incident.affected_tables == affected_tables
    assert incident.first_seen_at <= incident.last_seen_at
    assert operation.ready_closure_ref is None


def test_structural_integrity_second_read_recovery_downgrades_to_commit_unavailable(
    tmp_path: Path,
) -> None:
    """First read fails with HIDDEN_SUMMARY_DIGEST_MISMATCH; second read recovers to COMPLETE.

    This proves bounded re-read downgrade to class (a), not structural observed-drift rejection.
    Structural drift rejection is owned by ``test_integrity_confirmed_rejects_drifting_structural_observed_digest``.
    """
    from gateway_backend.application.history.contracts import HistoryCompareDiagnosticCode

    commit_id = BASELINE_HEAD.business_baseline_commit_id
    commit_b = "commit-b"
    provider = _provider_for_integrity_scenario("structural_second_read_recovers", commit_id)
    harness = build_history_compare_harness(
        tmp_path,
        custom_providers={
            commit_id: provider,
            commit_b: history_compare_provider(commit_id=commit_b),
        },
        idempotency_key="history-compare-f5-structural-second-read-recovery",
    )
    insert_history_compare_operation(harness)
    run_through_step(harness, HISTORY_COMPARE_MATERIALIZE_HANDLER)

    with ControlDbUnitOfWork(harness.db_path, read_only=True) as unit_of_work:
        operation = unit_of_work.operations.get_operation(harness.operation_id)
        incident = unit_of_work.history_compare.get_integrity_by_operation_id(harness.operation_id)
    assert operation.status is OperationStatus.FAILED
    assert operation.diagnostic is not None
    assert (
        operation.diagnostic.code
        == HistoryCompareDiagnosticCode.HISTORY_COMMIT_UNAVAILABLE.value
    )
    assert incident is None
    assert operation.ready_closure_ref is None


def test_integrity_confirmed_allows_drifting_observed_digest() -> None:
    from gateway_shared_kernel import DigestRef

    from gateway_backend.application.history.compare_jobs import _integrity_confirmed
    from gateway_backend.capabilities.snapshot_materialization.contracts import (
        DiagnosticSeverity,
        MaterializationDiagnostic,
        MaterializationDiagnosticCode,
    )

    expected = DigestRef("sha256:" + "a" * 64)
    first = MaterializationDiagnostic(
        code=MaterializationDiagnosticCode.HIDDEN_SUMMARY_DIGEST_MISMATCH,
        severity=DiagnosticSeverity.ERROR,
        message="first",
        expected_digest_ref=expected,
        observed_digest_ref=DigestRef("sha256:" + "b" * 64),
    )
    second = MaterializationDiagnostic(
        code=MaterializationDiagnosticCode.HIDDEN_SUMMARY_DIGEST_MISMATCH,
        severity=DiagnosticSeverity.ERROR,
        message="second",
        expected_digest_ref=expected,
        observed_digest_ref=DigestRef("sha256:" + "c" * 64),
    )
    assert _integrity_confirmed(first, second)


def test_integrity_confirmed_rejects_drifting_structural_observed_digest() -> None:
    from gateway_shared_kernel import raw_blob_digest

    from gateway_backend.application.history.compare_jobs import _integrity_confirmed
    from gateway_backend.capabilities.snapshot_materialization.contracts import (
        DiagnosticSeverity,
        MaterializationDiagnostic,
        MaterializationDiagnosticCode,
    )

    expected = raw_blob_digest(b"catalog-table:t")
    first = MaterializationDiagnostic(
        code=MaterializationDiagnosticCode.HIDDEN_SUMMARY_DIGEST_MISMATCH,
        severity=DiagnosticSeverity.ERROR,
        message="first",
        table="t",
        expected_digest_ref=expected,
        observed_digest_ref=raw_blob_digest(b"catalog-table:missing"),
    )
    second = MaterializationDiagnostic(
        code=MaterializationDiagnosticCode.HIDDEN_SUMMARY_DIGEST_MISMATCH,
        severity=DiagnosticSeverity.ERROR,
        message="second",
        table="t",
        expected_digest_ref=expected,
        observed_digest_ref=raw_blob_digest(b"hidden-summary-table:missing:t"),
    )
    assert not _integrity_confirmed(first, second)


def test_pending_integrity_blocks_new_compare_until_acknowledged(tmp_path: Path) -> None:
    harness = build_history_compare_harness(
        tmp_path,
        mutate_snapshot_digest_for=frozenset({BASELINE_HEAD.business_baseline_commit_id}),
        idempotency_key="history-compare-block",
    )
    insert_history_compare_operation(harness)
    run_through_step(harness, HISTORY_COMPARE_MATERIALIZE_HANDLER)

    with ControlDbUnitOfWork(harness.db_path, read_only=True) as unit_of_work:
        pending = unit_of_work.history_compare.has_pending_integrity_for_commit(
            repository_id="repo-1",
            commit_id=BASELINE_HEAD.business_baseline_commit_id,
        )
    assert pending is True

    with ControlDbUnitOfWork(harness.db_path) as unit_of_work:
        unit_of_work.history_compare.save_integrity_record(
            HistoryCompareIntegrityRecord(
                incident_id="hci-manual",
                operation_id="op-manual",
                repository_id="repo-1",
                commit_refs=({"commit_id": "commit-b"},),
                failure_class=HISTORY_INTEGRITY_FAILURE_CLASS,
                expected_digest="sha256:" + "a" * 64,
                observed_digest="sha256:" + "b" * 64,
                affected_tables=(),
                recommended_action=HISTORY_INTEGRITY_RECOMMENDED_ACTION,
                first_seen_at=TS,
                last_seen_at=TS,
                acknowledgement_status=IntegrityAcknowledgementStatus.PENDING,
                resolution_reference=None,
                created_at=TS,
                updated_at=TS,
            )
        )
        assert unit_of_work.history_compare.has_pending_integrity_for_commit(
            repository_id="repo-1",
            commit_id="commit-b",
        )

    acknowledge_integrity_incident(
        operation_id=harness.operation_id,
        acknowledgement_status=IntegrityAcknowledgementStatus.ACKNOWLEDGED.value,
        resolution_reference="ticket-ack",
        unit_of_work_factory=lambda *, read_only=False: ControlDbUnitOfWork(
            harness.db_path,
            read_only=read_only,
        ),
        now=TS,
    )
    with ControlDbUnitOfWork(harness.db_path, read_only=True) as unit_of_work:
        assert not unit_of_work.history_compare.has_pending_integrity_for_commit(
            repository_id="repo-1",
            commit_id=BASELINE_HEAD.business_baseline_commit_id,
        )

