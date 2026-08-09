"""Real Dolt subprocess crash tests for all ImportWorkerFaultPoint values."""

from __future__ import annotations

import time
from pathlib import Path
from uuid import UUID

import pytest

from gateway_repository_contracts import OperationStatus
from gateway_repository_service.control_db import CONTROL_DB_USER_VERSION, ControlStore
from gateway_repository_service.layout import DurableLayout
from gateway_repository_service.process import DoltRunner
from gateway_repository_service.upload_artifact.visibility import artifact_ready_path
from gateway_repository_service.versioned_import.faults import ImportWorkerFaultPoint
from gateway_repository_service.versioned_import.models import (
    MANUAL_RECOVERY_REQUIRED_CODE,
    derive_private_ref_name,
)
from gateway_repository_service.versioned_import.provider import CandidateAImportProvider
from gateway_repository_service.versioned_import.store import ImportOperationStore
from gateway_repository_service.versioned_import.verification import IMPORT_REJECTED_CODE
from support.import_recovery_harness import (
    assert_crash_exit,
    crash_import_subprocess,
    restart_runtime,
    seed_queued_dolt_import,
)
from support.import_dolt_crash_evidence import assert_crash_state_evidence, assert_final_state_evidence
from support.import_worker_harness import published_repository_path

_FAULT_POINTS = list(ImportWorkerFaultPoint)

_POST_CRASH_SUCCEEDED = {
    ImportWorkerFaultPoint.AFTER_SUCCEEDED_BEFORE_PRIVATE_REF_CLEANUP,
    ImportWorkerFaultPoint.AFTER_SUCCEEDED_BEFORE_ARTIFACT_CLEANUP,
}

_FINAL_SUCCEEDED = {
    ImportWorkerFaultPoint.AFTER_RUNNING_CLAIM,
    ImportWorkerFaultPoint.AFTER_PACKAGE_EXTRACTED,
    ImportWorkerFaultPoint.AFTER_REPLAY_BEFORE_MARKER,
    ImportWorkerFaultPoint.AFTER_MARKER_BEFORE_VERIFICATION,
    ImportWorkerFaultPoint.AFTER_VERIFICATION_BEFORE_SECOND_MAIN_CHECK,
    ImportWorkerFaultPoint.AFTER_SECOND_MAIN_CHECK_BEFORE_PUBLISH,
    ImportWorkerFaultPoint.AFTER_MAIN_PUBLISH_BEFORE_SUCCEEDED,
    ImportWorkerFaultPoint.AFTER_SUCCEEDED_BEFORE_PRIVATE_REF_CLEANUP,
    ImportWorkerFaultPoint.AFTER_SUCCEEDED_BEFORE_ARTIFACT_CLEANUP,
}

_FINAL_MANUAL = {
    ImportWorkerFaultPoint.AFTER_PRIVATE_REF_CREATED,
}

_EXPECTED_REPLAY_COUNT = {
    ImportWorkerFaultPoint.AFTER_RUNNING_CLAIM: 1,
    ImportWorkerFaultPoint.AFTER_PACKAGE_EXTRACTED: 1,
    ImportWorkerFaultPoint.AFTER_PRIVATE_REF_CREATED: 0,
    ImportWorkerFaultPoint.AFTER_REPLAY_BEFORE_MARKER: 0,
    ImportWorkerFaultPoint.AFTER_MARKER_BEFORE_VERIFICATION: 0,
    ImportWorkerFaultPoint.AFTER_VERIFICATION_BEFORE_SECOND_MAIN_CHECK: 0,
    ImportWorkerFaultPoint.AFTER_SECOND_MAIN_CHECK_BEFORE_PUBLISH: 0,
    ImportWorkerFaultPoint.AFTER_MAIN_PUBLISH_BEFORE_SUCCEEDED: 0,
    ImportWorkerFaultPoint.AFTER_SUCCEEDED_BEFORE_PRIVATE_REF_CLEANUP: 0,
    ImportWorkerFaultPoint.AFTER_SUCCEEDED_BEFORE_ARTIFACT_CLEANUP: 0,
}


def _provider_for(
    settings: object,
    layout: DurableLayout,
    repository_id: UUID,
) -> CandidateAImportProvider:
    from gateway_repository_service.settings import RepositoryServiceSettings

    assert isinstance(settings, RepositoryServiceSettings)
    repository = published_repository_path(layout, repository_id)
    runner = DoltRunner(settings, layout.root)
    return CandidateAImportProvider(settings, layout, repository, runner)


def _wait_for_terminal(
    runtime: object,
    repository_id: UUID,
    operation_id: UUID,
    *,
    timeout: float = 90.0,
) -> OperationStatus:
    from gateway_repository_service.runtime import ServiceRuntime

    assert isinstance(runtime, ServiceRuntime)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        operation = runtime.import_store.get_operation(repository_id, operation_id)
        if operation is not None and operation.status in {
            OperationStatus.SUCCEEDED,
            OperationStatus.FAILED,
        }:
            return operation.status
        time.sleep(0.1)
    raise AssertionError(f"operation {operation_id} did not reach a terminal state")


@pytest.mark.integration
@pytest.mark.serial
@pytest.mark.parametrize("fault_point", _FAULT_POINTS, ids=[point.value for point in _FAULT_POINTS])
def test_dolt_crash_recovery(tmp_path: Path, fault_point: ImportWorkerFaultPoint) -> None:
    settings, repository_id, artifact_id, operation_id, expected_commit = seed_queued_dolt_import(
        tmp_path,
        key=f"crash-{fault_point.value}",
    )

    completed = crash_import_subprocess(
        settings,
        repository_id=repository_id,
        operation_id=operation_id,
        fault_point=fault_point.value,
    )
    assert_crash_exit(completed)

    control_store = ControlStore.open(
        settings.control_db_path,
        expected_version=CONTROL_DB_USER_VERSION,
        busy_timeout_ms=1000,
    )
    store = ImportOperationStore(
        control_store.connection,
        transaction_lock=control_store.transaction_lock,
    )
    crashed = store.get_operation(repository_id, operation_id)
    assert crashed is not None
    if fault_point in _POST_CRASH_SUCCEEDED:
        assert crashed.status == OperationStatus.SUCCEEDED
    else:
        assert crashed.status == OperationStatus.RUNNING
    replay_count_after_crash = store.get_automatic_replay_count(operation_id)

    layout = DurableLayout.create_for_probe(settings.data_root)
    crash_provider = _provider_for(settings, layout, repository_id)
    assert_crash_state_evidence(
        fault_point=fault_point,
        provider=crash_provider,
        store=store,
        layout=layout,
        repository_id=repository_id,
        operation_id=operation_id,
        expected_commit=expected_commit,
    )
    control_store.close()

    runtime = restart_runtime(settings)
    try:
        terminal = _wait_for_terminal(runtime, repository_id, operation_id)
        operation = runtime.import_store.get_operation(repository_id, operation_id)
        assert operation is not None

        if fault_point in _FINAL_SUCCEEDED:
            assert terminal == OperationStatus.SUCCEEDED
            assert operation.result is not None
            assert operation.result.expected_commit_id == expected_commit
            provider = _provider_for(settings, runtime.layout, repository_id)
            private_ref = derive_private_ref_name(operation_id)
            assert not provider.private_ref_exists(private_ref)
            artifact_path = artifact_ready_path(runtime.layout, repository_id, artifact_id)
            deadline = time.monotonic() + 30.0
            while time.monotonic() < deadline:
                lifecycle = runtime.mutation_store.get_artifact_lifecycle(artifact_id)
                if lifecycle is not None and lifecycle.bytes_deleted_at is not None and not artifact_path.exists():
                    break
                time.sleep(0.1)
            else:
                raise AssertionError("artifact cleanup did not complete after recovery")
        elif fault_point in _FINAL_MANUAL:
            assert terminal == OperationStatus.FAILED
            assert operation.error is not None
            assert operation.error.code == MANUAL_RECOVERY_REQUIRED_CODE
            provider = _provider_for(settings, runtime.layout, repository_id)
            private_ref = derive_private_ref_name(operation_id)
            assert provider.private_ref_exists(private_ref)
            assert artifact_ready_path(runtime.layout, repository_id, artifact_id).exists()
        else:
            assert terminal == OperationStatus.FAILED
            assert operation.error is not None
            assert operation.error.code in {
                IMPORT_REJECTED_CODE,
                MANUAL_RECOVERY_REQUIRED_CODE,
            }

        replay_count = runtime.import_store.get_automatic_replay_count(operation_id)
        assert replay_count == _EXPECTED_REPLAY_COUNT[fault_point]
        assert replay_count >= replay_count_after_crash

        provider = _provider_for(settings, runtime.layout, repository_id)
        assert_final_state_evidence(
            fault_point=fault_point,
            provider=provider,
            store=runtime.import_store,
            layout=runtime.layout,
            repository_id=repository_id,
            operation_id=operation_id,
            expected_commit=expected_commit,
            terminal=terminal,
        )

        if (
            fault_point == ImportWorkerFaultPoint.AFTER_MAIN_PUBLISH_BEFORE_SUCCEEDED
            and terminal == OperationStatus.SUCCEEDED
        ):
            assert operation.result is not None
            provider = _provider_for(settings, runtime.layout, repository_id)
            assert provider.read_ref("main") == operation.result.commit_id

        if (
            fault_point == ImportWorkerFaultPoint.AFTER_MARKER_BEFORE_VERIFICATION
            and terminal == OperationStatus.SUCCEEDED
        ):
            assert operation.operation_marker
            assert operation.result is not None
            provider = _provider_for(settings, runtime.layout, repository_id)
            assert provider.read_ref("main") == operation.result.commit_id

        if fault_point == ImportWorkerFaultPoint.AFTER_REPLAY_BEFORE_MARKER:
            runtime.shutdown()
            runtime = restart_runtime(settings)
            try:
                operation = runtime.import_store.get_operation(repository_id, operation_id)
                assert operation is not None
                assert operation.status == OperationStatus.SUCCEEDED
                assert runtime.import_store.get_automatic_replay_count(operation_id) == replay_count
            finally:
                runtime.shutdown()
            return
    finally:
        runtime.shutdown()
