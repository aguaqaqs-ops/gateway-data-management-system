"""Durable evidence helpers for real Dolt import crash-recovery tests."""

from __future__ import annotations

from uuid import UUID

from gateway_repository_contracts import OperationStatus
from gateway_repository_service.versioned_import.models import derive_private_ref_name
from gateway_repository_service.versioned_import.provider import CandidateAImportProvider
from gateway_repository_service.versioned_import.store import ImportOperationStore
from gateway_repository_service.versioned_import.faults import ImportWorkerFaultPoint


def records_row_count(provider: CandidateAImportProvider) -> int:
    try:
        rows = provider._cli.query_json(  # noqa: SLF001
            "records_count",
            "SELECT COUNT(*) AS row_count FROM records;\n",
        )
    except Exception:
        return 0
    if not rows:
        return 0
    row = rows[0]
    raw = row.get("row_count", row.get("COUNT(*)", 0))
    return int(raw)


def assert_early_fault_evidence(
    *,
    provider: CandidateAImportProvider,
    operation_id: UUID,
    expected_commit: str,
) -> None:
    private_ref = derive_private_ref_name(operation_id)
    assert not provider.private_ref_exists(private_ref)
    assert provider.read_ref("main") == expected_commit
    assert records_row_count(provider) == 0


def assert_private_ref_created_evidence(
    *,
    provider: CandidateAImportProvider,
    operation_id: UUID,
    expected_commit: str,
) -> None:
    private_ref = derive_private_ref_name(operation_id)
    assert provider.private_ref_exists(private_ref)
    assert provider.read_ref("main") == expected_commit


def assert_succeeded_fault_evidence(
    *,
    provider: CandidateAImportProvider,
    operation_id: UUID,
    result_commit_id: str,
    expected_commit: str,
) -> None:
    private_ref = derive_private_ref_name(operation_id)
    assert not provider.private_ref_exists(private_ref)
    assert provider.read_ref("main") == result_commit_id
    assert records_row_count(provider) == 1


def assert_replay_once_evidence(
    *,
    provider: CandidateAImportProvider,
    expected_rows: int = 1,
) -> None:
    assert records_row_count(provider) == expected_rows


def assert_fault_point_evidence(
    *,
    fault_point: ImportWorkerFaultPoint,
    provider: CandidateAImportProvider,
    store: ImportOperationStore,
    repository_id: UUID,
    operation_id: UUID,
    expected_commit: str,
    terminal: OperationStatus,
) -> None:
    operation = store.get_operation(repository_id, operation_id)
    assert operation is not None

    if fault_point in {
        ImportWorkerFaultPoint.AFTER_RUNNING_CLAIM,
        ImportWorkerFaultPoint.AFTER_PACKAGE_EXTRACTED,
    }:
        if terminal == OperationStatus.SUCCEEDED:
            assert_succeeded_fault_evidence(
                provider=provider,
                operation_id=operation_id,
                result_commit_id=operation.result.commit_id if operation.result else expected_commit,
                expected_commit=expected_commit,
            )
        else:
            assert_early_fault_evidence(
                provider=provider,
                operation_id=operation_id,
                expected_commit=expected_commit,
            )
        return

    if fault_point == ImportWorkerFaultPoint.AFTER_PRIVATE_REF_CREATED:
        if terminal == OperationStatus.FAILED:
            assert_private_ref_created_evidence(
                provider=provider,
                operation_id=operation_id,
                expected_commit=expected_commit,
            )
        return

    if terminal == OperationStatus.SUCCEEDED:
        assert operation.result is not None
        assert_succeeded_fault_evidence(
            provider=provider,
            operation_id=operation_id,
            result_commit_id=operation.result.commit_id,
            expected_commit=expected_commit,
        )
        assert_replay_once_evidence(provider=provider)
        if fault_point == ImportWorkerFaultPoint.AFTER_MARKER_BEFORE_VERIFICATION:
            assert operation.operation_marker
