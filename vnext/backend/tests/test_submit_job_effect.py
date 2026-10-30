"""Repository upload/import wire-mapping and handler-level submit effect tests."""

from __future__ import annotations

import json
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast
from uuid import UUID

import httpx
import pytest
from gateway_repository_contracts import (
    REPOSITORY_IMPORT_MEDIA_TYPE,
    UnknownTypePolicy,
    VerificationPolicy,
)
from gateway_backend.domain.submission.models import RepositoryArtifactRef
from gateway_backend.application.checkpoints import load_checkpoint_envelope
from gateway_backend.application.payloads import CheckpointDecodeError
from gateway_backend.application.recovery import (
    DIAGNOSTIC_MANUAL_RECOVERY_REQUIRED,
    RecoveryOutcomeDisposition,
)
import gateway_backend.application.submit_jobs as submit_jobs
from gateway_backend.application.submit_jobs import (
    SUBMIT_IMPORT_POLL_DEADLINE_SECONDS,
    SUBMIT_IMPORT_WAIT_UPPER_BOUND_SECONDS,
    _prepare_checkpoint_from_job_state,
    build_await_import_result_handler,
    build_submit_operator_recovery_port,
    build_submit_import_handler,
)
from gateway_backend.application.submission.contracts import (
    RepositoryImportOperation,
    RepositoryImportOperationStatus,
)
from gateway_backend.application.submission.errors import (
    RepositoryUploadMetadataMismatch,
    RepositoryWriteTransportError,
    RepositoryWriteTimeoutError,
)
from gateway_backend.application.submission.job_payload import (
    SUBMIT_STEP_AWAIT,
    SUBMIT_STEP_PREPARE,
    SUBMIT_STEP_SUBMIT,
)
from gateway_backend.bootstrap.operation_worker import build_worker_write_uow_factory
from gateway_backend.domain.submission.models import SubmitAttemptState
from gateway_backend.infrastructure.control_db import ControlDbUnitOfWork
from gateway_backend.infrastructure.repository_write.http import HttpRepositoryWriteClient
from gateway_backend.application.submission.ports import (
    RepositoryAbortEvidencePort,
    RepositoryWritePort,
    SubmitControlTransaction,
)
from gateway_backend.operations import (
    OperationStatus,
    StepStatus,
    TransitionDisposition,
    WritePrecondition,
)
from gateway_backend.operations.contracts import OperationRecord, StepRecord
from gateway_backend.operations.lease_session import LeaseSession
from gateway_backend.operations.recovery import (
    DIAGNOSTIC_WAIT_UPPER_BOUND_EXCEEDED,
    OperatorRecoveryCommand,
    OperatorRecoveryRequest,
    RecoveryCapabilityValue,
)
from gateway_backend.operations.state import DIAGNOSTIC_HEALTHY_WAIT_HANDOFF
from gateway_backend.operations.worker import (
    ClaimedWork,
    ExecutionControl,
    ExecutorAcknowledgment,
    StartupDisposition,
    WriteUnitOfWorkFactory,
)
from tests.support.submit_job_harness import (
    RecordingTransport,
    SubmitWorkerHarness,
    build_submit_worker_harness,
    default_repository_handler,
    repository_service_session,
    submit_step_id,
)
from tests.test_submit_job_prepare import _accept_prepared_operation, _run_prepare_handler

pytestmark = pytest.mark.integration

REPOSITORY_ID = "018f0f3e-7b0a-7c15-8a9e-2e4b9f4d2c11"
ARTIFACT_ID = "018f0f3e-7b0a-7c16-8a9e-2e4b9f4d2c11"
UPLOAD_KEY = "upload-idem-submit-effect"
IMPORT_KEY = "import-idem-submit-effect"
PACKAGE_BYTES = b"submit-package-bytes"
PACKAGE_SHA256 = "b" * 64
EXPECTED_COMMIT_ID = "commit-main"
EXPECTED_PARENT_COMMIT_ID = "commit-base"


def _import_request_body(repository_artifact_ref: RepositoryArtifactRef) -> dict[str, object]:
    return {
        "repository_id": REPOSITORY_ID,
        "artifact_ref": {
            "artifact_id": repository_artifact_ref.artifact_id,
            "media_type": REPOSITORY_IMPORT_MEDIA_TYPE,
            "size_bytes": repository_artifact_ref.size_bytes,
            "raw_sha256": repository_artifact_ref.raw_sha256,
        },
        "target_ref": "main",
        "expected_commit_id": EXPECTED_COMMIT_ID,
        "verification_policy": VerificationPolicy.STRUCTURAL.value,
        "unknown_type_policy": UnknownTypePolicy.REJECT.value,
    }


def test_submit_upload_and_import_wire_mapping_uses_recording_transport() -> None:
    transport = RecordingTransport()
    client = HttpRepositoryWriteClient(
        base_url="http://repository.test",
        bearer_token="test-bearer-token",
        transport=transport,
    )
    repository_artifact_ref = client.upload_artifact(
        repository_id=REPOSITORY_ID,
        idempotency_key=UPLOAD_KEY,
        media_type=REPOSITORY_IMPORT_MEDIA_TYPE,
        raw_sha256=PACKAGE_SHA256,
        body=PACKAGE_BYTES,
    )
    operation_id = client.submit_versioned_import(
        repository_id=REPOSITORY_ID,
        idempotency_key=IMPORT_KEY,
        artifact_ref=repository_artifact_ref,
        expected_commit_id=EXPECTED_COMMIT_ID,
    )

    assert len(transport.requests) == 2
    upload = transport.requests[0]
    import_request = transport.requests[1]

    assert upload.method == "POST"
    assert upload.url == f"http://repository.test/v1/repositories/{REPOSITORY_ID}/artifacts"
    assert upload.headers["authorization"] == "Bearer test-bearer-token"
    assert upload.headers["idempotency-key"] == UPLOAD_KEY
    assert upload.headers["content-type"] == REPOSITORY_IMPORT_MEDIA_TYPE
    assert upload.headers["content-length"] == str(len(PACKAGE_BYTES))
    assert upload.headers["x-artifact-sha256"] == PACKAGE_SHA256
    assert upload.body == PACKAGE_BYTES

    assert import_request.method == "POST"
    assert (
        import_request.url
        == f"http://repository.test/v1/repositories/{REPOSITORY_ID}/versioned/imports"
    )
    assert import_request.headers["authorization"] == "Bearer test-bearer-token"
    assert import_request.headers["idempotency-key"] == IMPORT_KEY
    assert import_request.headers["content-type"] == "application/json"
    assert json.loads(import_request.body) == _import_request_body(repository_artifact_ref)
    assert set(json.loads(import_request.body)) == {
        "repository_id",
        "artifact_ref",
        "target_ref",
        "expected_commit_id",
        "verification_policy",
        "unknown_type_policy",
    }
    assert operation_id == "018f0f3e-7b0a-7c17-8a9e-2e4b9f4d2c11"


@pytest.mark.integration
def test_submit_upload_and_import_wire_mapping_against_live_repository(
    tmp_path: Path,
    requires_dolt: None,
) -> None:
    with repository_service_session(tmp_path) as service:
        seeded = service.repository_id_factory(idempotency_key="create-submit-effect-live")
        transport = RecordingTransport()
        client = service.write_client(transport=transport)
        repository_artifact_ref = client.upload_artifact(
            repository_id=seeded.repository_id,
            idempotency_key=UPLOAD_KEY,
            media_type=REPOSITORY_IMPORT_MEDIA_TYPE,
            raw_sha256=PACKAGE_SHA256,
            body=PACKAGE_BYTES,
        )
        operation_id = client.submit_versioned_import(
            repository_id=seeded.repository_id,
            idempotency_key=IMPORT_KEY,
            artifact_ref=repository_artifact_ref,
            expected_commit_id=seeded.initial_commit_id,
        )

    upload = transport.requests[0]
    import_request = transport.requests[1]
    assert upload.url.endswith(f"/v1/repositories/{seeded.repository_id}/artifacts")
    assert upload.headers["idempotency-key"] == UPLOAD_KEY
    assert import_request.url.endswith(f"/v1/repositories/{seeded.repository_id}/versioned/imports")
    assert import_request.headers["idempotency-key"] == IMPORT_KEY
    body = json.loads(import_request.body)
    assert body["repository_id"] == seeded.repository_id
    assert body["expected_commit_id"] == seeded.initial_commit_id
    assert body["target_ref"] == "main"
    assert body["verification_policy"] == VerificationPolicy.STRUCTURAL.value
    assert body["unknown_type_policy"] == UnknownTypePolicy.REJECT.value
    assert set(body) == {
        "repository_id",
        "artifact_ref",
        "target_ref",
        "expected_commit_id",
        "verification_policy",
        "unknown_type_policy",
    }
    UUID(operation_id)


_HANDLER_REPOSITORY_UUID = "018f0f3e-7b0a-7c15-8a9e-2e4b9f4d2c11"


def _lease_session(
    harness: SubmitWorkerHarness,
    *,
    worker_id: str,
    lease_token: str,
    operation_id: str,
    step_id: str,
) -> tuple[ExecutionControl, LeaseSession]:
    def control_transaction_factory() -> ControlDbUnitOfWork:
        return ControlDbUnitOfWork(harness.db_path)

    control = ExecutionControl()
    session = LeaseSession(
        worker_id=worker_id,
        lease_token=lease_token,
        operation_id=operation_id,
        step_id=step_id,
        write_uow_factory=build_worker_write_uow_factory(control_transaction_factory),
        control=control,
        observer=lambda _event: None,
    )
    return control, session


def _await_lease_identity(await_work: ClaimedWork) -> tuple[str, str]:
    worker_id = await_work.step.worker_id
    lease_token = await_work.step.lease_token
    if worker_id is None or lease_token is None:
        raise AssertionError("await step lease identity is missing")
    return worker_id, lease_token


def _worker_write_uow_factory(harness: SubmitWorkerHarness) -> WriteUnitOfWorkFactory:
    def control_transaction_factory() -> ControlDbUnitOfWork:
        return ControlDbUnitOfWork(harness.db_path)

    return build_worker_write_uow_factory(control_transaction_factory)


def _unused_submit_control_uow_factory(
    *, read_only: bool = False
) -> AbstractContextManager[SubmitControlTransaction]:
    del read_only
    raise AssertionError("Submit abort recovery is not exercised by this test")


def _run_submit_to_await_claim(
    harness: SubmitWorkerHarness,
) -> tuple[ClaimedWork, str]:
    operation_id = _accept_prepared_operation(
        harness.db_path,
        harness.artifact_store,
        repository_id=_HANDLER_REPOSITORY_UUID,
    )
    _run_prepare_handler(harness.db_path, harness.artifact_store, operation_id)
    startup = harness.runtime._startup
    assert startup.startup() is StartupDisposition.READY
    submit_work = startup.claim_one()
    assert submit_work is not None
    assert submit_work.step.step_name == SUBMIT_STEP_SUBMIT
    assert submit_work.step.worker_id is not None
    assert submit_work.step.lease_token is not None
    submit_control, submit_session = _lease_session(
        harness,
        worker_id=submit_work.step.worker_id,
        lease_token=submit_work.step.lease_token,
        operation_id=submit_work.operation.operation_id,
        step_id=submit_work.step.step_id,
    )
    assert (
        submit_work.executor(
            submit_work.operation,
            submit_work.step,
            submit_control,
            submit_session,
        )
        is ExecutorAcknowledgment.PUBLISHED
    )
    await_work = startup.claim_one()
    assert await_work is not None
    assert await_work.step.step_name == SUBMIT_STEP_AWAIT
    assert await_work.step.worker_id is not None
    assert await_work.step.lease_token is not None
    return await_work, operation_id


class _ImmediatePollTimeout:
    def __init__(self, delegate: object) -> None:
        self._delegate = delegate
        self.deadlines: list[float | None] = []

    def __getattr__(self, name: str) -> object:
        return getattr(self._delegate, name)

    def wait_operation(
        self,
        *,
        repository_id: str,
        operation_id: str,
        deadline_seconds: float | None = None,
    ) -> object:
        del repository_id, operation_id
        self.deadlines.append(deadline_seconds)
        raise RepositoryWriteTimeoutError("simulated bounded Repository poll timeout")


class _ImmediatePollTransportError:
    def __init__(self, delegate: object) -> None:
        self._delegate = delegate

    def __getattr__(self, name: str) -> object:
        return getattr(self._delegate, name)

    def wait_operation(
        self,
        *,
        repository_id: str,
        operation_id: str,
        deadline_seconds: float | None = None,
    ) -> RepositoryImportOperation:
        del repository_id, operation_id, deadline_seconds
        raise RepositoryWriteTransportError("simulated unknown poll result")


class _ImmediateOperationIdentityMismatch:
    def __init__(self, delegate: object) -> None:
        self._delegate = delegate

    def __getattr__(self, name: str) -> object:
        return getattr(self._delegate, name)

    def wait_operation(
        self,
        *,
        repository_id: str,
        operation_id: str,
        deadline_seconds: float | None = None,
    ) -> RepositoryImportOperation:
        del repository_id, deadline_seconds
        return RepositoryImportOperation(
            operation_id="00000000-0000-0000-0000-000000000099",
            status=RepositoryImportOperationStatus.RUNNING,
        )


class _InjectedPollClock:
    def __init__(self, wall_time: datetime, *, sleep_advance_seconds: float = 0.0) -> None:
        self.wall_time = wall_time
        self.monotonic_time = 0.0
        self.sleep_advance_seconds = sleep_advance_seconds
        self.sleep_calls: list[float] = []

    def now(self) -> datetime:
        return self.wall_time

    def monotonic(self) -> float:
        return self.monotonic_time

    async def sleep(self, seconds: float) -> None:
        self.sleep_calls.append(seconds)
        elapsed = max(seconds, self.sleep_advance_seconds)
        self.wall_time += timedelta(seconds=elapsed)
        self.monotonic_time += elapsed

    def advance_wall(self, seconds: float) -> None:
        self.wall_time += timedelta(seconds=seconds)


class _RecordingPollClient:
    def __init__(self, delegate: object) -> None:
        self._delegate = delegate
        self.deadlines: list[float | None] = []

    def __getattr__(self, name: str) -> object:
        return getattr(self._delegate, name)

    def wait_operation(
        self,
        *,
        repository_id: str,
        operation_id: str,
        deadline_seconds: float | None = None,
    ) -> RepositoryImportOperation:
        self.deadlines.append(deadline_seconds)
        delegate = cast(RepositoryWritePort, self._delegate)
        return delegate.wait_operation(
            repository_id=repository_id,
            operation_id=operation_id,
            deadline_seconds=deadline_seconds,
        )


def _prepare_manifest_digest(harness: SubmitWorkerHarness, operation_id: str) -> str:
    with ControlDbUnitOfWork(harness.db_path, read_only=True) as unit_of_work:
        operation = unit_of_work.operations.get_operation(operation_id)
        submit_attempt_id = next(
            ref.value for ref in operation.business_refs if ref.kind == "submit_attempt"
        )
        prepare_step = unit_of_work.operations.get_step(
            submit_step_id(operation_id, SUBMIT_STEP_PREPARE)
        )
    assert prepare_step.checkpoint_ref is not None
    envelope = load_checkpoint_envelope(harness.artifact_store, prepare_step.checkpoint_ref)
    prepare_checkpoint = _prepare_checkpoint_from_job_state(
        envelope.job_state,
        expected_attempt_id=submit_attempt_id,
    )
    return prepare_checkpoint.canonicalization_manifest_digest


def _timeout_await_step_until_manual_recovery(
    harness: SubmitWorkerHarness,
    await_work: ClaimedWork,
    operation_id: str,
) -> tuple[OperationRecord, StepRecord]:
    for expected_attempt in range(1, 4):
        assert await_work.step.attempt_count == expected_attempt
        timeout_client = _ImmediatePollTimeout(harness.submit_deps.repository_write)
        deps = replace(
            harness.submit_deps,
            repository_write=cast(RepositoryWritePort, timeout_client),
        )
        handler = build_await_import_result_handler(deps)
        worker_id, lease_token = _await_lease_identity(await_work)
        control, session = _lease_session(
            harness,
            worker_id=worker_id,
            lease_token=lease_token,
            operation_id=operation_id,
            step_id=await_work.step.step_id,
        )
        assert (
            handler(await_work.operation, await_work.step, control, session)
            is ExecutorAcknowledgment.PUBLISHED
        )
        with ControlDbUnitOfWork(harness.db_path, read_only=True) as unit_of_work:
            operation = unit_of_work.operations.get_operation(operation_id)
            step = unit_of_work.operations.get_step(
                submit_step_id(operation_id, SUBMIT_STEP_AWAIT)
            )
        if expected_attempt == 3:
            assert operation.status is OperationStatus.MANUAL_RECOVERY_REQUIRED
            assert step.status is StepStatus.MANUAL_RECOVERY_REQUIRED
            return operation, step

        assert step.status is StepStatus.RETRY_WAIT
        with ControlDbUnitOfWork(harness.db_path) as unit_of_work:
            transaction_now = unit_of_work.operations.transaction_now
            due_step = replace(
                step,
                retry_not_before=transaction_now,
                updated_at=transaction_now,
                optimistic_version=step.optimistic_version + 1,
            )
            assert (
                unit_of_work.operations.compare_and_set_step(
                    due_step,
                    WritePrecondition(
                        expected_optimistic_version=step.optimistic_version,
                        worker_id=None,
                        lease_token=None,
                    ),
                )
                is TransitionDisposition.APPLY
            )
        await_work = harness.runtime._startup.claim_one()
        assert await_work is not None
    raise AssertionError("three reconcile sessions did not reach manual recovery")


def _resume_manual_await_and_claim(harness: SubmitWorkerHarness, operation_id: str) -> ClaimedWork:
    with ControlDbUnitOfWork(harness.db_path, read_only=True) as unit_of_work:
        operation = unit_of_work.operations.get_operation(operation_id)
        step = unit_of_work.operations.get_step(
            submit_step_id(operation_id, SUBMIT_STEP_AWAIT)
        )
    operator = build_submit_operator_recovery_port(
        write_uow_factory=_worker_write_uow_factory(harness),
        capability_lookup=lambda _job_kind, _step_name: RecoveryCapabilityValue.EXTERNAL_EFFECT,
        submit_control_uow_factory=_unused_submit_control_uow_factory,
        abort_evidence=cast(RepositoryAbortEvidencePort, object()),
        submit_deps=harness.submit_deps,
    )
    request = OperatorRecoveryRequest(
        command=OperatorRecoveryCommand.RESUME_RECONCILE,
        operation_id=operation_id,
        step_id=step.step_id,
        expected_operation_optimistic_version=operation.optimistic_version,
        expected_step_optimistic_version=step.optimistic_version,
        reason="resume the bounded Submit reconciliation test",
    )
    assert operator.execute_recovery(request) is TransitionDisposition.APPLY
    # _run_submit_to_await_claim already started this worker; it claims the resumed
    # step without constructing or restarting the worker runtime.
    startup = harness.runtime._startup
    work = cast(ClaimedWork | None, startup.claim_one())
    assert work is not None
    assert work.step.step_name == SUBMIT_STEP_AWAIT
    assert work.step.attempt_count == 4
    return work


def _operation_poll_handler(
    manifest_digest: str,
    *,
    operation_id_override: str | None = None,
    expected_commit_id: str = EXPECTED_PARENT_COMMIT_ID,
    completed_verification_policy: str = VerificationPolicy.STRUCTURAL.value,
    unknown_type_policy: str = UnknownTypePolicy.REJECT.value,
) -> Callable[[httpx.Request], httpx.Response]:
    def handler(request: httpx.Request) -> httpx.Response:
        if "/operations/" in request.url.path and request.method == "GET":
            operation_id = request.url.path.rsplit("/", 1)[-1]
            if operation_id_override is not None:
                operation_id = operation_id_override
            return httpx.Response(
                200,
                json={
                    "operation": {
                        "operation_id": operation_id,
                        "status": "SUCCEEDED",
                        "error": None,
                        "result": {
                            "commit_id": "commit-c1",
                            "target_ref": "main",
                            "artifact_id": "018f0f3e-7b0a-7c16-8a9e-2e4b9f4d2c11",
                            "canonicalization_manifest_digest": manifest_digest,
                            "expected_commit_id": expected_commit_id,
                            "completed_verification_policy": completed_verification_policy,
                            "unknown_type_policy": unknown_type_policy,
                        },
                    }
                },
                headers={"X-Request-ID": "req-operation"},
            )
        return default_repository_handler(request)

    return handler


@pytest.mark.serial
def test_healthy_repository_waits_do_not_consume_sessions_or_grow_checkpoints(
    tmp_path: Path,
) -> None:
    control_clock = {"value": datetime.now(UTC)}
    harness = build_submit_worker_harness(
        tmp_path,
        repository_base_url="http://repository.test",
        transport=RecordingTransport(default_repository_handler),
        control_clock=control_clock,
    )
    await_work, operation_id = _run_submit_to_await_claim(harness)
    manifest_digest = _prepare_manifest_digest(harness, operation_id)
    clock = _InjectedPollClock(
        await_work.step.started_at or control_clock["value"],
        sleep_advance_seconds=SUBMIT_IMPORT_POLL_DEADLINE_SECONDS,
    )
    poll_count = 0

    def _healthy_until_third_poll(request: httpx.Request) -> httpx.Response:
        nonlocal poll_count
        if "/operations/" not in request.url.path or request.method != "GET":
            return default_repository_handler(request)
        poll_count += 1
        if poll_count < 3:
            operation_id_from_path = request.url.path.rsplit("/", 1)[-1]
            return httpx.Response(
                200,
                json={
                    "operation": {
                        "operation_id": operation_id_from_path,
                        "status": "QUEUED" if poll_count == 1 else "RUNNING",
                        "error": None,
                        "result": None,
                    }
                },
                headers={"X-Request-ID": "req-operation"},
            )
        return _operation_poll_handler(manifest_digest)(request)

    transport = RecordingTransport(_healthy_until_third_poll)
    write_client = replace(
        cast(HttpRepositoryWriteClient, harness.submit_deps.repository_write),
        transport=transport,
        clock=clock.monotonic,
        sleeper=clock.sleep,
    )
    poll_client = _RecordingPollClient(write_client)
    deps = replace(
        harness.submit_deps,
        repository_write=cast(RepositoryWritePort, poll_client),
        now_factory=clock.now,
    )
    handler = build_await_import_result_handler(deps)

    checkpoint_artifacts_after_first_wait: frozenset[str] | None = None
    for handoff_number in range(2):
        worker_id, lease_token = _await_lease_identity(await_work)
        control, session = _lease_session(
            harness,
            worker_id=worker_id,
            lease_token=lease_token,
            operation_id=operation_id,
            step_id=await_work.step.step_id,
        )
        assert (
            handler(await_work.operation, await_work.step, control, session)
            is ExecutorAcknowledgment.SAFE_HANDOFF
        )
        with ControlDbUnitOfWork(harness.db_path, read_only=True) as unit_of_work:
            current_step = unit_of_work.operations.get_step(
                submit_step_id(operation_id, SUBMIT_STEP_AWAIT)
            )
        assert current_step.status is StepStatus.RETRY_WAIT
        assert current_step.attempt_count == 1
        assert current_step.diagnostic is not None
        assert current_step.diagnostic.code == DIAGNOSTIC_HEALTHY_WAIT_HANDOFF
        if handoff_number == 0:
            checkpoint_artifacts_after_first_wait = frozenset(
                harness.artifact_store._artifacts
            )
        else:
            assert checkpoint_artifacts_after_first_wait is not None
            assert frozenset(harness.artifact_store._artifacts) == (
                checkpoint_artifacts_after_first_wait
            )

        await_work = harness.runtime._startup.claim_one()
        assert await_work is not None
        assert await_work.step.step_name == SUBMIT_STEP_AWAIT
        assert await_work.step.attempt_count == 1
        assert await_work.step.diagnostic is None

    worker_id, lease_token = _await_lease_identity(await_work)
    control, session = _lease_session(
        harness,
        worker_id=worker_id,
        lease_token=lease_token,
        operation_id=operation_id,
        step_id=await_work.step.step_id,
    )
    assert (
        handler(await_work.operation, await_work.step, control, session)
        is ExecutorAcknowledgment.PUBLISHED
    )
    assert poll_count == 3
    assert poll_client.deadlines == [SUBMIT_IMPORT_POLL_DEADLINE_SECONDS] * 3
    assert len(transport.requests) == 3
    with ControlDbUnitOfWork(harness.db_path, read_only=True) as unit_of_work:
        operation = unit_of_work.operations.get_operation(operation_id)
        submit_attempt_id = next(
            ref.value for ref in operation.business_refs if ref.kind == "submit_attempt"
        )
        attempt = unit_of_work.submission.get_submit_attempt(submit_attempt_id)
        assert attempt is not None
        submission = unit_of_work.submission.get_submission_by_attempt(
            attempt.submit_attempt_id
        )
    assert operation.status is OperationStatus.SUCCEEDED
    assert attempt.state is SubmitAttemptState.FINALIZED
    assert submission is not None


@pytest.mark.serial
def test_healthy_wait_past_repository_bound_requires_manual_recovery(tmp_path: Path) -> None:
    control_clock = {"value": datetime.now(UTC)}
    harness = build_submit_worker_harness(
        tmp_path,
        repository_base_url="http://repository.test",
        transport=RecordingTransport(default_repository_handler),
        control_clock=control_clock,
    )
    await_work, operation_id = _run_submit_to_await_claim(harness)
    started_at = await_work.step.started_at
    assert started_at is not None
    clock = _InjectedPollClock(started_at + timedelta(seconds=3_600))

    class _SlowHealthyClient:
        def __init__(self, delegate: object) -> None:
            self._delegate = delegate
            self.deadlines: list[float | None] = []

        def __getattr__(self, name: str) -> object:
            return getattr(self._delegate, name)

        def wait_operation(
            self,
            *,
            repository_id: str,
            operation_id: str,
            deadline_seconds: float | None = None,
        ) -> RepositoryImportOperation:
            del repository_id
            self.deadlines.append(deadline_seconds)
            clock.advance_wall((deadline_seconds or 0.0) + 1.0)
            return RepositoryImportOperation(
                operation_id=operation_id,
                status=RepositoryImportOperationStatus.RUNNING,
            )

    slow_client = _SlowHealthyClient(harness.submit_deps.repository_write)
    deps = replace(
        harness.submit_deps,
        repository_write=cast(RepositoryWritePort, slow_client),
        now_factory=clock.now,
    )
    worker_id, lease_token = _await_lease_identity(await_work)
    control, session = _lease_session(
        harness,
        worker_id=worker_id,
        lease_token=lease_token,
        operation_id=operation_id,
        step_id=await_work.step.step_id,
    )
    handler = build_await_import_result_handler(deps)
    assert (
        handler(await_work.operation, await_work.step, control, session)
        is ExecutorAcknowledgment.PUBLISHED
    )
    assert slow_client.deadlines == [30.0]
    with ControlDbUnitOfWork(harness.db_path, read_only=True) as unit_of_work:
        operation = unit_of_work.operations.get_operation(operation_id)
        step = unit_of_work.operations.get_step(
            submit_step_id(operation_id, SUBMIT_STEP_AWAIT)
        )
    assert SUBMIT_IMPORT_WAIT_UPPER_BOUND_SECONDS == 3_600.0 + 30.0
    assert operation.status is OperationStatus.MANUAL_RECOVERY_REQUIRED
    assert step.status is StepStatus.MANUAL_RECOVERY_REQUIRED
    assert step.diagnostic is not None
    assert step.diagnostic.code == DIAGNOSTIC_WAIT_UPPER_BOUND_EXCEEDED.upper()
    assert "超出等待上界" in step.diagnostic.message


@pytest.mark.serial
def test_drain_and_shutdown_handoff_after_one_bounded_poll(tmp_path: Path) -> None:
    control_clock = {"value": datetime.now(UTC)}
    harness = build_submit_worker_harness(
        tmp_path,
        repository_base_url="http://repository.test",
        transport=RecordingTransport(default_repository_handler),
        control_clock=control_clock,
    )
    await_work, operation_id = _run_submit_to_await_claim(harness)
    clock = _InjectedPollClock(
        await_work.step.started_at or control_clock["value"],
        sleep_advance_seconds=SUBMIT_IMPORT_POLL_DEADLINE_SECONDS,
    )
    control = ExecutionControl()

    def _drain_during_poll(request: httpx.Request) -> httpx.Response:
        if "/operations/" not in request.url.path or request.method != "GET":
            return default_repository_handler(request)
        control.request_drain()
        repository_operation_id = request.url.path.rsplit("/", 1)[-1]
        return httpx.Response(
            200,
            json={
                "operation": {
                    "operation_id": repository_operation_id,
                    "status": "RUNNING",
                    "error": None,
                    "result": None,
                }
            },
        )

    transport = RecordingTransport(_drain_during_poll)
    write_client = replace(
        cast(HttpRepositoryWriteClient, harness.submit_deps.repository_write),
        transport=transport,
        clock=clock.monotonic,
        sleeper=clock.sleep,
    )
    poll_client = _RecordingPollClient(write_client)
    deps = replace(
        harness.submit_deps,
        repository_write=cast(RepositoryWritePort, poll_client),
        now_factory=clock.now,
    )
    handler = build_await_import_result_handler(deps)
    worker_id, lease_token = _await_lease_identity(await_work)
    session = LeaseSession(
        worker_id=worker_id,
        lease_token=lease_token,
        operation_id=operation_id,
        step_id=await_work.step.step_id,
        write_uow_factory=_worker_write_uow_factory(harness),
        control=control,
        observer=lambda _event: None,
    )

    assert (
        handler(await_work.operation, await_work.step, control, session)
        is ExecutorAcknowledgment.SAFE_HANDOFF
    )
    assert control.drain_requested
    assert poll_client.deadlines == [SUBMIT_IMPORT_POLL_DEADLINE_SECONDS]
    assert len(transport.requests) == 1
    with ControlDbUnitOfWork(harness.db_path, read_only=True) as unit_of_work:
        step = unit_of_work.operations.get_step(
            submit_step_id(operation_id, SUBMIT_STEP_AWAIT)
        )
    assert step.status is StepStatus.RETRY_WAIT
    assert step.attempt_count == 1


COUNTED_POLL_FAILURE_CLIENTS: tuple[str, ...] = (
    "transport_error",
    "operation_identity_mismatch",
)


@pytest.mark.serial
@pytest.mark.parametrize("failure_kind", COUNTED_POLL_FAILURE_CLIENTS)
def test_transport_and_identity_failures_exhaust_three_reconcile_sessions(
    tmp_path: Path,
    failure_kind: str,
) -> None:
    harness = build_submit_worker_harness(
        tmp_path,
        repository_base_url="http://repository.test",
        transport=RecordingTransport(default_repository_handler),
    )
    await_work, operation_id = _run_submit_to_await_claim(harness)
    client_type = {
        "transport_error": _ImmediatePollTransportError,
        "operation_identity_mismatch": _ImmediateOperationIdentityMismatch,
    }[failure_kind]
    deps = replace(
        harness.submit_deps,
        repository_write=cast(
            RepositoryWritePort,
            client_type(harness.submit_deps.repository_write),
        ),
    )
    handler = build_await_import_result_handler(deps)

    for attempt_number in range(1, 4):
        assert await_work.step.attempt_count == attempt_number
        worker_id, lease_token = _await_lease_identity(await_work)
        control, session = _lease_session(
            harness,
            worker_id=worker_id,
            lease_token=lease_token,
            operation_id=operation_id,
            step_id=await_work.step.step_id,
        )
        assert (
            handler(await_work.operation, await_work.step, control, session)
            is ExecutorAcknowledgment.PUBLISHED
        )
        with ControlDbUnitOfWork(harness.db_path, read_only=True) as unit_of_work:
            operation = unit_of_work.operations.get_operation(operation_id)
            step = unit_of_work.operations.get_step(
                submit_step_id(operation_id, SUBMIT_STEP_AWAIT)
            )
        if attempt_number == 3:
            assert step.status is StepStatus.MANUAL_RECOVERY_REQUIRED
            assert operation.status is OperationStatus.MANUAL_RECOVERY_REQUIRED
            assert step.attempt_count == 3
            break

        assert step.status is StepStatus.RETRY_WAIT
        with ControlDbUnitOfWork(harness.db_path) as unit_of_work:
            transaction_now = unit_of_work.operations.transaction_now
            due_step = replace(
                step,
                retry_not_before=transaction_now,
                updated_at=transaction_now,
                optimistic_version=step.optimistic_version + 1,
            )
            assert (
                unit_of_work.operations.compare_and_set_step(
                    due_step,
                    WritePrecondition(
                        expected_optimistic_version=step.optimistic_version,
                        worker_id=None,
                        lease_token=None,
                    ),
                )
                is TransitionDisposition.APPLY
            )
        await_work = harness.runtime._startup.claim_one()
        assert await_work is not None
    else:
        raise AssertionError("counted poll failure did not exhaust the three-session budget")


def _run_await_with_poll_handler(
    tmp_path: Path,
    poll_handler: Callable[[httpx.Request], httpx.Response],
) -> tuple[SubmitWorkerHarness, str, OperationStatus, SubmitAttemptState]:
    harness = build_submit_worker_harness(
        tmp_path,
        repository_base_url="http://repository.test",
        transport=RecordingTransport(),
    )
    await_work, operation_id = _run_submit_to_await_claim(harness)
    write_client = cast(HttpRepositoryWriteClient, harness.submit_deps.repository_write)
    await_write = replace(
        write_client,
        transport=RecordingTransport(
            lambda request: (
                poll_handler(request)
                if "/operations/" in request.url.path and request.method == "GET"
                else default_repository_handler(request)
            )
        ),
    )
    await_deps = replace(harness.submit_deps, repository_write=await_write)
    worker_id, lease_token = _await_lease_identity(await_work)
    control, session = _lease_session(
        harness,
        worker_id=worker_id,
        lease_token=lease_token,
        operation_id=await_work.operation.operation_id,
        step_id=await_work.step.step_id,
    )
    handler = build_await_import_result_handler(await_deps)
    handler(await_work.operation, await_work.step, control, session)
    with ControlDbUnitOfWork(harness.db_path, read_only=True) as unit_of_work:
        operation = unit_of_work.operations.get_operation(operation_id)
        submit_attempt_id = next(
            ref.value for ref in operation.business_refs if ref.kind == "submit_attempt"
        )
        attempt = unit_of_work.submission.get_submit_attempt(submit_attempt_id)
        assert attempt is not None
        return harness, operation_id, operation.status, attempt.state


def test_await_import_result_succeeded_finalizes_submission(tmp_path: Path) -> None:
    harness = build_submit_worker_harness(
        tmp_path,
        repository_base_url="http://repository.test",
        transport=RecordingTransport(),
    )
    await_work, operation_id = _run_submit_to_await_claim(harness)
    manifest_digest = _prepare_manifest_digest(harness, operation_id)
    write_client = cast(HttpRepositoryWriteClient, harness.submit_deps.repository_write)
    await_write = replace(
        write_client,
        transport=RecordingTransport(_operation_poll_handler(manifest_digest)),
    )
    await_deps = replace(harness.submit_deps, repository_write=await_write)
    worker_id, lease_token = _await_lease_identity(await_work)
    control, session = _lease_session(
        harness,
        worker_id=worker_id,
        lease_token=lease_token,
        operation_id=await_work.operation.operation_id,
        step_id=await_work.step.step_id,
    )
    handler = build_await_import_result_handler(await_deps)
    assert (
        handler(await_work.operation, await_work.step, control, session)
        is ExecutorAcknowledgment.PUBLISHED
    )
    with ControlDbUnitOfWork(harness.db_path, read_only=True) as unit_of_work:
        operation = unit_of_work.operations.get_operation(operation_id)
        submit_attempt_id = next(
            ref.value for ref in operation.business_refs if ref.kind == "submit_attempt"
        )
        attempt = unit_of_work.submission.get_submit_attempt(submit_attempt_id)
        assert attempt is not None
        submission = unit_of_work.submission.get_submission_by_attempt(attempt.submit_attempt_id)
    assert operation.status is OperationStatus.SUCCEEDED
    assert attempt.state is SubmitAttemptState.FINALIZED
    assert submission is not None


SUBMIT_IMPORT_POLL_TIMEOUT_CASES: tuple[
    tuple[int, StepStatus, OperationStatus], ...
] = (
    (1, StepStatus.RETRY_WAIT, OperationStatus.RUNNING),
    (2, StepStatus.RETRY_WAIT, OperationStatus.RUNNING),
    (3, StepStatus.MANUAL_RECOVERY_REQUIRED, OperationStatus.MANUAL_RECOVERY_REQUIRED),
)


@pytest.mark.serial
@pytest.mark.parametrize(
    ("poll_sessions", "expected_step_status", "expected_operation_status"),
    SUBMIT_IMPORT_POLL_TIMEOUT_CASES,
)
def test_await_import_result_timeout_uses_bounded_submit_poll_sessions(
    tmp_path: Path,
    poll_sessions: int,
    expected_step_status: StepStatus,
    expected_operation_status: OperationStatus,
) -> None:
    harness = build_submit_worker_harness(
        tmp_path,
        repository_base_url="http://repository.test",
        transport=RecordingTransport(default_repository_handler),
    )
    await_work, operation_id = _run_submit_to_await_claim(harness)
    with ControlDbUnitOfWork(harness.db_path, read_only=True) as unit_of_work:
        submit_step = unit_of_work.operations.get_step(
            submit_step_id(operation_id, SUBMIT_STEP_SUBMIT)
        )
    assert submit_step.checkpoint_ref is not None
    submit_checkpoint = load_checkpoint_envelope(
        harness.artifact_store,
        submit_step.checkpoint_ref,
    )
    assert "reconcile_started_at" not in submit_checkpoint.job_state
    recorder = _ImmediatePollTimeout(harness.submit_deps.repository_write)
    timeout_deps = replace(
        harness.submit_deps,
        repository_write=cast(RepositoryWritePort, recorder),
    )
    handler = build_await_import_result_handler(timeout_deps)

    for session_number in range(1, poll_sessions + 1):
        assert await_work.step.attempt_count == session_number
        worker_id, lease_token = _await_lease_identity(await_work)
        control, session = _lease_session(
            harness,
            worker_id=worker_id,
            lease_token=lease_token,
            operation_id=operation_id,
            step_id=await_work.step.step_id,
        )
        assert (
            handler(await_work.operation, await_work.step, control, session)
            is ExecutorAcknowledgment.PUBLISHED
        )
        with ControlDbUnitOfWork(harness.db_path, read_only=True) as unit_of_work:
            operation = unit_of_work.operations.get_operation(operation_id)
            current_step = unit_of_work.operations.get_step(
                submit_step_id(operation_id, SUBMIT_STEP_AWAIT)
            )
        assert current_step.checkpoint_ref is not None
        await_checkpoint = load_checkpoint_envelope(
            harness.artifact_store,
            current_step.checkpoint_ref,
        )
        assert "reconcile_started_at" not in await_checkpoint.job_state
        assert operation.status is (
            expected_operation_status
            if session_number == poll_sessions
            else OperationStatus.RUNNING
        )
        assert current_step.status is (
            expected_step_status if session_number == poll_sessions else StepStatus.RETRY_WAIT
        )
        if session_number < poll_sessions:
            with ControlDbUnitOfWork(harness.db_path) as unit_of_work:
                transaction_now = unit_of_work.operations.transaction_now
                due_step = replace(
                    current_step,
                    retry_not_before=transaction_now,
                    updated_at=transaction_now,
                    optimistic_version=current_step.optimistic_version + 1,
                )
                assert (
                    unit_of_work.operations.compare_and_set_step(
                        due_step,
                        WritePrecondition(
                            expected_optimistic_version=current_step.optimistic_version,
                            worker_id=None,
                            lease_token=None,
                        ),
                    )
                    is TransitionDisposition.APPLY
                )
            await_work = harness.runtime._startup.claim_one()
            assert await_work is not None
            assert await_work.step.step_name == SUBMIT_STEP_AWAIT

    assert recorder.deadlines == [SUBMIT_IMPORT_POLL_DEADLINE_SECONDS] * poll_sessions


@pytest.mark.serial
def test_resume_reconcile_claimed_by_running_worker_completes_submit(
    tmp_path: Path,
) -> None:
    transport = RecordingTransport(default_repository_handler)
    harness = build_submit_worker_harness(
        tmp_path,
        repository_base_url="http://repository.test",
        transport=transport,
    )
    await_work, operation_id = _run_submit_to_await_claim(harness)
    _timeout_await_step_until_manual_recovery(harness, await_work, operation_id)
    manifest_digest = _prepare_manifest_digest(harness, operation_id)
    transport._handler = _operation_poll_handler(manifest_digest)
    work = _resume_manual_await_and_claim(harness, operation_id)
    worker_id, lease_token = _await_lease_identity(work)
    control, session = _lease_session(
        harness,
        worker_id=worker_id,
        lease_token=lease_token,
        operation_id=operation_id,
        step_id=work.step.step_id,
    )

    assert (
        work.executor(work.operation, work.step, control, session)
        is ExecutorAcknowledgment.PUBLISHED
    )
    with ControlDbUnitOfWork(harness.db_path, read_only=True) as unit_of_work:
        operation = unit_of_work.operations.get_operation(operation_id)
        submit_attempt_id = next(
            ref.value for ref in operation.business_refs if ref.kind == "submit_attempt"
        )
        attempt = unit_of_work.submission.get_submit_attempt(submit_attempt_id)
        assert attempt is not None
        submission = unit_of_work.submission.get_submission_by_attempt(
            attempt.submit_attempt_id
        )
    assert operation.status is OperationStatus.SUCCEEDED
    assert attempt.state is SubmitAttemptState.FINALIZED
    assert submission is not None


@pytest.mark.serial
def test_resume_reconcile_counted_failure_returns_to_manual_recovery(
    tmp_path: Path,
) -> None:
    harness = build_submit_worker_harness(
        tmp_path,
        repository_base_url="http://repository.test",
        transport=RecordingTransport(default_repository_handler),
    )
    await_work, operation_id = _run_submit_to_await_claim(harness)
    _timeout_await_step_until_manual_recovery(harness, await_work, operation_id)
    work = _resume_manual_await_and_claim(harness, operation_id)
    timeout_client = _ImmediatePollTimeout(harness.submit_deps.repository_write)
    deps = replace(
        harness.submit_deps,
        repository_write=cast(RepositoryWritePort, timeout_client),
    )
    handler = build_await_import_result_handler(deps)
    worker_id, lease_token = _await_lease_identity(work)
    control, session = _lease_session(
        harness,
        worker_id=worker_id,
        lease_token=lease_token,
        operation_id=operation_id,
        step_id=work.step.step_id,
    )

    assert handler(work.operation, work.step, control, session) is ExecutorAcknowledgment.PUBLISHED
    with ControlDbUnitOfWork(harness.db_path, read_only=True) as unit_of_work:
        operation = unit_of_work.operations.get_operation(operation_id)
        step = unit_of_work.operations.get_step(
            submit_step_id(operation_id, SUBMIT_STEP_AWAIT)
        )
    assert step.attempt_count == 4
    assert step.status is StepStatus.MANUAL_RECOVERY_REQUIRED
    assert operation.status is OperationStatus.MANUAL_RECOVERY_REQUIRED


def test_await_import_result_disallowed_failure_marks_manual_recovery(tmp_path: Path) -> None:
    def _disallowed_failure_handler(request: httpx.Request) -> httpx.Response:
        if "/operations/" in request.url.path and request.method == "GET":
            operation_id = request.url.path.rsplit("/", 1)[-1]
            return httpx.Response(
                200,
                json={
                    "operation": {
                        "operation_id": operation_id,
                        "status": "FAILED",
                        "error": {
                            "code": "MANUAL_RECOVERY_REQUIRED",
                            "message": "not an allowed stable abort",
                            "request_id": None,
                        },
                        "result": None,
                    }
                },
                headers={"X-Request-ID": "req-operation"},
            )
        return default_repository_handler(request)

    harness = build_submit_worker_harness(
        tmp_path,
        repository_base_url="http://repository.test",
        transport=RecordingTransport(_disallowed_failure_handler),
    )
    await_work, operation_id = _run_submit_to_await_claim(harness)
    worker_id, lease_token = _await_lease_identity(await_work)
    control, session = _lease_session(
        harness,
        worker_id=worker_id,
        lease_token=lease_token,
        operation_id=await_work.operation.operation_id,
        step_id=await_work.step.step_id,
    )
    handler = build_await_import_result_handler(harness.submit_deps)
    assert (
        handler(await_work.operation, await_work.step, control, session)
        is ExecutorAcknowledgment.PUBLISHED
    )
    with ControlDbUnitOfWork(harness.db_path, read_only=True) as unit_of_work:
        operation = unit_of_work.operations.get_operation(operation_id)
        submit_attempt_id = next(
            ref.value for ref in operation.business_refs if ref.kind == "submit_attempt"
        )
        attempt = unit_of_work.submission.get_submit_attempt(submit_attempt_id)
        assert attempt is not None
        workspace_occupancy = unit_of_work.submission.get_workspace_occupancy(attempt.workspace_id)
    assert operation.status is OperationStatus.MANUAL_RECOVERY_REQUIRED
    assert operation.diagnostic is not None
    assert operation.diagnostic.code == DIAGNOSTIC_MANUAL_RECOVERY_REQUIRED.upper()
    assert workspace_occupancy is not None


@pytest.mark.parametrize("failure_kind", ("transport", "request_fingerprint"))
def test_transport_and_request_fingerprint_failures_are_counted_reconcile_outcomes(
    failure_kind: str,
) -> None:
    error: BaseException
    if failure_kind == "transport":
        error = RepositoryWriteTransportError("Repository operation result is unknown")
    else:
        error = CheckpointDecodeError(
            "submit checkpoint request_fingerprint does not match payload semantics",
            code=submit_jobs._EXTERNAL_EFFECT_IDENTITY_MISMATCH_CHECKPOINT_CODE,
        )
    outcome = submit_jobs._map_handler_failure_to_recovery_outcome(error)
    assert outcome is not None
    assert outcome.disposition is RecoveryOutcomeDisposition.RECONCILE_PENDING


def _run_await_binding_mismatch_case(
    tmp_path: Path,
    *,
    operation_id_override: str | None = None,
    expected_commit_id: str | None = None,
    completed_verification_policy: str | None = None,
    unknown_type_policy: str | None = None,
) -> tuple[OperationStatus, SubmitAttemptState, StepStatus, int, str | None]:
    harness = build_submit_worker_harness(
        tmp_path,
        repository_base_url="http://repository.test",
        transport=RecordingTransport(),
    )
    await_work, operation_id = _run_submit_to_await_claim(harness)
    manifest_digest = _prepare_manifest_digest(harness, operation_id)
    poll_handler = _operation_poll_handler(
        manifest_digest,
        operation_id_override=operation_id_override,
        expected_commit_id=expected_commit_id or EXPECTED_PARENT_COMMIT_ID,
        completed_verification_policy=completed_verification_policy
        or VerificationPolicy.STRUCTURAL.value,
        unknown_type_policy=unknown_type_policy or UnknownTypePolicy.REJECT.value,
    )
    write_client = cast(HttpRepositoryWriteClient, harness.submit_deps.repository_write)
    await_write = replace(
        write_client,
        transport=RecordingTransport(
            lambda request: (
                poll_handler(request)
                if "/operations/" in request.url.path and request.method == "GET"
                else default_repository_handler(request)
            )
        ),
    )
    await_deps = replace(harness.submit_deps, repository_write=await_write)
    worker_id, lease_token = _await_lease_identity(await_work)
    control, session = _lease_session(
        harness,
        worker_id=worker_id,
        lease_token=lease_token,
        operation_id=await_work.operation.operation_id,
        step_id=await_work.step.step_id,
    )
    handler = build_await_import_result_handler(await_deps)
    handler(await_work.operation, await_work.step, control, session)
    with ControlDbUnitOfWork(harness.db_path, read_only=True) as unit_of_work:
        operation = unit_of_work.operations.get_operation(operation_id)
        submit_attempt_id = next(
            ref.value for ref in operation.business_refs if ref.kind == "submit_attempt"
        )
        attempt = unit_of_work.submission.get_submit_attempt(submit_attempt_id)
        assert attempt is not None
        step = unit_of_work.operations.get_step(submit_step_id(operation_id, SUBMIT_STEP_AWAIT))
        return (
            operation.status,
            attempt.state,
            step.status,
            step.attempt_count,
            None if step.diagnostic is None else step.diagnostic.code,
        )


def test_await_import_rejects_mismatched_repository_operation_id(tmp_path: Path) -> None:
    (
        operation_status,
        attempt_state,
        step_status,
        attempt_count,
        diagnostic_code,
    ) = _run_await_binding_mismatch_case(
        tmp_path,
        operation_id_override="00000000-0000-0000-0000-000000000099",
    )
    assert operation_status is OperationStatus.RUNNING
    assert attempt_state is SubmitAttemptState.EFFECT_PENDING
    assert step_status is StepStatus.RETRY_WAIT
    assert attempt_count == 1
    assert diagnostic_code == "R5.EFFECT_IDENTITY_MISMATCH"


def test_await_import_rejects_mismatched_expected_commit_id(tmp_path: Path) -> None:
    (
        operation_status,
        attempt_state,
        step_status,
        _attempt_count,
        _diagnostic_code,
    ) = _run_await_binding_mismatch_case(
        tmp_path,
        expected_commit_id="commit-wrong",
    )
    assert operation_status is OperationStatus.MANUAL_RECOVERY_REQUIRED
    assert attempt_state is SubmitAttemptState.EFFECT_PENDING
    assert step_status is StepStatus.MANUAL_RECOVERY_REQUIRED


def test_await_import_rejects_mismatched_verification_policy(tmp_path: Path) -> None:
    (
        operation_status,
        attempt_state,
        step_status,
        _attempt_count,
        _diagnostic_code,
    ) = _run_await_binding_mismatch_case(
        tmp_path,
        completed_verification_policy=VerificationPolicy.FULL_SCAN.value,
    )
    assert operation_status is OperationStatus.MANUAL_RECOVERY_REQUIRED
    assert attempt_state is SubmitAttemptState.EFFECT_PENDING
    assert step_status is StepStatus.MANUAL_RECOVERY_REQUIRED


def test_await_import_rejects_mismatched_unknown_type_policy(tmp_path: Path) -> None:
    (
        operation_status,
        attempt_state,
        step_status,
        _attempt_count,
        _diagnostic_code,
    ) = _run_await_binding_mismatch_case(
        tmp_path,
        unknown_type_policy=UnknownTypePolicy.STRINGIFY.value,
    )
    assert operation_status is OperationStatus.MANUAL_RECOVERY_REQUIRED
    assert attempt_state is SubmitAttemptState.EFFECT_PENDING
    assert step_status is StepStatus.MANUAL_RECOVERY_REQUIRED


def test_upload_artifact_rejects_mismatched_response_metadata() -> None:
    def _bad_upload_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            201,
            json={
                "artifact_ref": {
                    "artifact_id": ARTIFACT_ID,
                    "media_type": "application/octet-stream",
                    "size_bytes": 999,
                    "raw_sha256": "0" * 64,
                }
            },
            headers={"X-Request-ID": "req-upload"},
        )

    client = HttpRepositoryWriteClient(
        base_url="http://repository.test",
        bearer_token="test-bearer-token",
        transport=RecordingTransport(_bad_upload_handler),
    )
    with pytest.raises(RepositoryUploadMetadataMismatch):
        client.upload_artifact(
            repository_id=REPOSITORY_ID,
            idempotency_key=UPLOAD_KEY,
            media_type=REPOSITORY_IMPORT_MEDIA_TYPE,
            raw_sha256=PACKAGE_SHA256,
            body=PACKAGE_BYTES,
        )


def test_submit_import_aborts_before_effect_pending_on_upload_metadata_mismatch(
    tmp_path: Path,
) -> None:
    harness = build_submit_worker_harness(
        tmp_path,
        repository_base_url="http://repository.test",
        transport=RecordingTransport(
            lambda request: (
                httpx.Response(
                    201,
                    json={
                        "artifact_ref": {
                            "artifact_id": ARTIFACT_ID,
                            "media_type": "application/octet-stream",
                            "size_bytes": 999,
                            "raw_sha256": "0" * 64,
                        }
                    },
                    headers={"X-Request-ID": "req-upload"},
                )
                if request.url.path.endswith("/artifacts")
                else default_repository_handler(request)
            )
        ),
    )
    operation_id = _accept_prepared_operation(
        harness.db_path,
        harness.artifact_store,
        repository_id=_HANDLER_REPOSITORY_UUID,
    )
    _run_prepare_handler(harness.db_path, harness.artifact_store, operation_id)
    startup = harness.runtime._startup
    assert startup.startup() is StartupDisposition.READY
    submit_work = startup.claim_one()
    assert submit_work is not None
    submit_control, submit_session = _lease_session(
        harness,
        worker_id=submit_work.step.worker_id or "",
        lease_token=submit_work.step.lease_token or "",
        operation_id=submit_work.operation.operation_id,
        step_id=submit_work.step.step_id,
    )
    handler = build_submit_import_handler(harness.submit_deps)
    with pytest.raises(RepositoryUploadMetadataMismatch):
        handler(
            submit_work.operation,
            submit_work.step,
            submit_control,
            submit_session,
        )
    with ControlDbUnitOfWork(harness.db_path, read_only=True) as unit_of_work:
        operation = unit_of_work.operations.get_operation(operation_id)
        submit_attempt_id = next(
            ref.value for ref in operation.business_refs if ref.kind == "submit_attempt"
        )
        attempt = unit_of_work.submission.get_submit_attempt(submit_attempt_id)
    assert attempt is not None
    assert attempt.state is SubmitAttemptState.PREPARED
    assert attempt.repository_artifact_ref is None


def test_await_import_pins_checkpoint_and_evidence_protection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _block_finalize(*args: object, **kwargs: object) -> object:
        raise RuntimeError("block finalize to inspect protection")

    monkeypatch.setattr(
        "gateway_backend.application.submit_jobs.finalize_submit_transaction",
        _block_finalize,
    )
    harness = build_submit_worker_harness(
        tmp_path,
        repository_base_url="http://repository.test",
        transport=RecordingTransport(),
    )
    await_work, operation_id = _run_submit_to_await_claim(harness)
    manifest_digest = _prepare_manifest_digest(harness, operation_id)
    write_client = cast(HttpRepositoryWriteClient, harness.submit_deps.repository_write)
    await_write = replace(
        write_client,
        transport=RecordingTransport(_operation_poll_handler(manifest_digest)),
    )
    await_deps = replace(harness.submit_deps, repository_write=await_write)
    worker_id, lease_token = _await_lease_identity(await_work)
    control, session = _lease_session(
        harness,
        worker_id=worker_id,
        lease_token=lease_token,
        operation_id=await_work.operation.operation_id,
        step_id=await_work.step.step_id,
    )
    handler = build_await_import_result_handler(await_deps)
    with pytest.raises(RuntimeError, match="block finalize to inspect protection"):
        handler(await_work.operation, await_work.step, control, session)
    with ControlDbUnitOfWork(harness.db_path, read_only=True) as unit_of_work:
        await_step = unit_of_work.operations.get_step(
            submit_step_id(operation_id, SUBMIT_STEP_AWAIT)
        )
        assert await_step.checkpoint_ref is not None
        envelope = load_checkpoint_envelope(harness.artifact_store, await_step.checkpoint_ref)
        evidence_ref = envelope.job_state.get("terminal_result_evidence_ref")
        assert type(evidence_ref) is dict
        assert unit_of_work.protection.is_protected(await_step.checkpoint_ref.artifact_id)
        assert unit_of_work.protection.is_protected(evidence_ref["artifact_id"])


def _assert_submit_checkpoint_protection_released(
    unit_of_work: ControlDbUnitOfWork,
    *,
    operation_id: str,
    submit_attempt_id: str,
) -> None:
    prepare_step = unit_of_work.operations.get_step(
        submit_step_id(operation_id, SUBMIT_STEP_PREPARE)
    )
    assert prepare_step.checkpoint_ref is not None
    assert not unit_of_work.protection.is_protected(prepare_step.checkpoint_ref.artifact_id)
    assert unit_of_work.list_artifact_protection_for_owner(
        owner_kind="submit-checkpoint",
        owner_id=submit_attempt_id,
    ) == frozenset()
    for step_name in (SUBMIT_STEP_PREPARE, SUBMIT_STEP_SUBMIT, SUBMIT_STEP_AWAIT):
        step = unit_of_work.operations.get_step(submit_step_id(operation_id, step_name))
        if step.checkpoint_ref is not None:
            assert not unit_of_work.protection.is_protected(step.checkpoint_ref.artifact_id)


def test_await_import_finalize_releases_checkpoint_protection(tmp_path: Path) -> None:
    harness = build_submit_worker_harness(
        tmp_path,
        repository_base_url="http://repository.test",
        transport=RecordingTransport(),
    )
    await_work, operation_id = _run_submit_to_await_claim(harness)
    manifest_digest = _prepare_manifest_digest(harness, operation_id)
    write_client = cast(HttpRepositoryWriteClient, harness.submit_deps.repository_write)
    await_write = replace(
        write_client,
        transport=RecordingTransport(_operation_poll_handler(manifest_digest)),
    )
    await_deps = replace(harness.submit_deps, repository_write=await_write)
    worker_id, lease_token = _await_lease_identity(await_work)
    control, session = _lease_session(
        harness,
        worker_id=worker_id,
        lease_token=lease_token,
        operation_id=await_work.operation.operation_id,
        step_id=await_work.step.step_id,
    )
    handler = build_await_import_result_handler(await_deps)
    handler(await_work.operation, await_work.step, control, session)
    with ControlDbUnitOfWork(harness.db_path, read_only=True) as unit_of_work:
        operation = unit_of_work.operations.get_operation(operation_id)
        submit_attempt_id = next(
            ref.value for ref in operation.business_refs if ref.kind == "submit_attempt"
        )
        await_step = unit_of_work.operations.get_step(
            submit_step_id(operation_id, SUBMIT_STEP_AWAIT)
        )
        assert await_step.checkpoint_ref is not None
        envelope = load_checkpoint_envelope(harness.artifact_store, await_step.checkpoint_ref)
        evidence_ref = envelope.job_state.get("terminal_result_evidence_ref")
        assert type(evidence_ref) is dict
        assert not unit_of_work.protection.is_protected(await_step.checkpoint_ref.artifact_id)
        assert not unit_of_work.protection.is_protected(evidence_ref["artifact_id"])
        _assert_submit_checkpoint_protection_released(
            unit_of_work,
            operation_id=operation_id,
            submit_attempt_id=submit_attempt_id,
        )


def test_await_import_stable_abort_releases_checkpoint_protection(tmp_path: Path) -> None:
    def _import_rejected_handler(request: httpx.Request) -> httpx.Response:
        if "/operations/" in request.url.path and request.method == "GET":
            operation_id = request.url.path.rsplit("/", 1)[-1]
            return httpx.Response(
                200,
                json={
                    "operation": {
                        "operation_id": operation_id,
                        "status": "FAILED",
                        "error": {
                            "code": "IMPORT_REJECTED",
                            "message": "import rejected",
                            "request_id": None,
                        },
                        "result": None,
                    }
                },
                headers={"X-Request-ID": "req-operation"},
            )
        return default_repository_handler(request)

    harness = build_submit_worker_harness(
        tmp_path,
        repository_base_url="http://repository.test",
        transport=RecordingTransport(_import_rejected_handler),
    )
    await_work, operation_id = _run_submit_to_await_claim(harness)
    worker_id, lease_token = _await_lease_identity(await_work)
    control, session = _lease_session(
        harness,
        worker_id=worker_id,
        lease_token=lease_token,
        operation_id=await_work.operation.operation_id,
        step_id=await_work.step.step_id,
    )
    handler = build_await_import_result_handler(harness.submit_deps)
    handler(await_work.operation, await_work.step, control, session)
    with ControlDbUnitOfWork(harness.db_path, read_only=True) as unit_of_work:
        operation = unit_of_work.operations.get_operation(operation_id)
        submit_attempt_id = next(
            ref.value for ref in operation.business_refs if ref.kind == "submit_attempt"
        )
        attempt = unit_of_work.submission.get_submit_attempt(submit_attempt_id)
        assert operation.status is OperationStatus.FAILED
        assert attempt is not None
        assert attempt.state is SubmitAttemptState.ABORTED
        _assert_submit_checkpoint_protection_released(
            unit_of_work,
            operation_id=operation_id,
            submit_attempt_id=submit_attempt_id,
        )


def test_await_import_persists_terminal_evidence_before_finalize(tmp_path: Path) -> None:
    harness = build_submit_worker_harness(
        tmp_path,
        repository_base_url="http://repository.test",
        transport=RecordingTransport(),
    )
    await_work, operation_id = _run_submit_to_await_claim(harness)
    manifest_digest = _prepare_manifest_digest(harness, operation_id)
    write_client = cast(HttpRepositoryWriteClient, harness.submit_deps.repository_write)
    await_write = replace(
        write_client,
        transport=RecordingTransport(_operation_poll_handler(manifest_digest)),
    )
    await_deps = replace(harness.submit_deps, repository_write=await_write)
    worker_id, lease_token = _await_lease_identity(await_work)
    control, session = _lease_session(
        harness,
        worker_id=worker_id,
        lease_token=lease_token,
        operation_id=await_work.operation.operation_id,
        step_id=await_work.step.step_id,
    )
    handler = build_await_import_result_handler(await_deps)
    handler(await_work.operation, await_work.step, control, session)
    with ControlDbUnitOfWork(harness.db_path, read_only=True) as unit_of_work:
        await_step = unit_of_work.operations.get_step(
            submit_step_id(operation_id, SUBMIT_STEP_AWAIT)
        )
    assert await_step.checkpoint_ref is not None
    envelope = load_checkpoint_envelope(harness.artifact_store, await_step.checkpoint_ref)
    assert envelope.job_state.get("last_observed_repository_status") == "SUCCEEDED"
    assert envelope.job_state.get("terminal_result_evidence_ref") is not None


def test_await_import_replays_t3_from_persisted_evidence_without_poll(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from gateway_backend.application.submission.finalize_transaction import finalize_submit_transaction

    finalize_calls = 0
    original_finalize = finalize_submit_transaction

    def _finalize_once_then_pass(*args: object, **kwargs: object) -> object:
        nonlocal finalize_calls
        finalize_calls += 1
        if finalize_calls == 1:
            raise RuntimeError("simulated crash before T3 commit")
        return original_finalize(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(
        "gateway_backend.application.submit_jobs.finalize_submit_transaction",
        _finalize_once_then_pass,
    )
    harness = build_submit_worker_harness(
        tmp_path,
        repository_base_url="http://repository.test",
        transport=RecordingTransport(),
    )
    await_work, operation_id = _run_submit_to_await_claim(harness)
    manifest_digest = _prepare_manifest_digest(harness, operation_id)
    write_client = cast(HttpRepositoryWriteClient, harness.submit_deps.repository_write)
    await_write = replace(
        write_client,
        transport=RecordingTransport(_operation_poll_handler(manifest_digest)),
    )
    await_deps = replace(harness.submit_deps, repository_write=await_write)
    worker_id, lease_token = _await_lease_identity(await_work)
    control, session = _lease_session(
        harness,
        worker_id=worker_id,
        lease_token=lease_token,
        operation_id=await_work.operation.operation_id,
        step_id=await_work.step.step_id,
    )
    handler = build_await_import_result_handler(await_deps)
    with pytest.raises(RuntimeError, match="simulated crash before T3 commit"):
        handler(await_work.operation, await_work.step, control, session)

    class _PollForbiddenClient:
        def wait_operation(
            self,
            *,
            repository_id: str,
            operation_id: str,
            deadline_seconds: float | None = None,
        ) -> object:
            raise AssertionError("wait_operation must not run when terminal evidence exists")

        def upload_artifact(
            self,
            *,
            repository_id: str,
            idempotency_key: str,
            media_type: str,
            raw_sha256: str,
            body: bytes,
        ) -> RepositoryArtifactRef:
            raise AssertionError("upload must not run during evidence replay")

        def submit_versioned_import(
            self,
            *,
            repository_id: str,
            idempotency_key: str,
            artifact_ref: RepositoryArtifactRef,
            expected_commit_id: str,
        ) -> str:
            raise AssertionError("import must not run during evidence replay")

        def get_operation(self, *, repository_id: str, operation_id: str) -> object:
            raise AssertionError("get_operation must not run during evidence replay")

        def canonical_import_request_bytes(
            self,
            *,
            repository_id: str,
            artifact_ref: RepositoryArtifactRef,
            expected_commit_id: str,
        ) -> bytes:
            from gateway_backend.infrastructure.repository_write import wire_codec

            return wire_codec.build_import_request_bytes(
                repository_id=repository_id,
                repository_artifact_ref=artifact_ref,
                expected_commit_id=expected_commit_id,
            )

    replay_deps = replace(
        await_deps,
        repository_write=cast(HttpRepositoryWriteClient, _PollForbiddenClient()),
    )
    with ControlDbUnitOfWork(harness.db_path, read_only=True) as unit_of_work:
        operation = unit_of_work.operations.get_operation(operation_id)
        await_step = unit_of_work.operations.get_step(
            submit_step_id(operation_id, SUBMIT_STEP_AWAIT)
        )
        assert await_step.checkpoint_ref is not None
        envelope = load_checkpoint_envelope(harness.artifact_store, await_step.checkpoint_ref)
        evidence_ref = envelope.job_state.get("terminal_result_evidence_ref")
        assert evidence_ref is not None
        assert type(evidence_ref) is dict
        assert unit_of_work.protection.is_protected(await_step.checkpoint_ref.artifact_id)
        assert unit_of_work.protection.is_protected(evidence_ref["artifact_id"])
    replay_handler = build_await_import_result_handler(replay_deps)
    replay_control, replay_session = _lease_session(
        harness,
        worker_id=worker_id,
        lease_token=lease_token,
        operation_id=operation.operation_id,
        step_id=await_step.step_id,
    )
    replay_handler(operation, await_step, replay_control, replay_session)
    with ControlDbUnitOfWork(harness.db_path, read_only=True) as unit_of_work:
        operation = unit_of_work.operations.get_operation(operation_id)
        submit_attempt_id = next(
            ref.value for ref in operation.business_refs if ref.kind == "submit_attempt"
        )
        attempt = unit_of_work.submission.get_submit_attempt(submit_attempt_id)
    assert operation.status is OperationStatus.SUCCEEDED
    assert attempt is not None
    assert attempt.state is SubmitAttemptState.FINALIZED
