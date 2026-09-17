"""Repository upload/import wire-mapping and handler-level submit effect tests."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import replace
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
from gateway_backend.application.recovery import DIAGNOSTIC_MANUAL_RECOVERY_REQUIRED
from gateway_backend.application.submit_jobs import (
    _prepare_checkpoint_from_job_state,
    build_await_import_result_handler,
    build_submit_import_handler,
)
from gateway_backend.application.submission.errors import RepositoryUploadMetadataMismatch
from gateway_backend.application.submission.job_payload import (
    SUBMIT_STEP_AWAIT,
    SUBMIT_STEP_PREPARE,
    SUBMIT_STEP_SUBMIT,
)
from gateway_backend.bootstrap.operation_worker import build_worker_write_uow_factory
from gateway_backend.domain.submission.models import SubmitAttemptState
from gateway_backend.infrastructure.control_db import ControlDbUnitOfWork
from gateway_backend.infrastructure.repository_write.http import HttpRepositoryWriteClient
from gateway_backend.operations import OperationStatus, StepStatus
from gateway_backend.operations.lease_session import LeaseSession
from gateway_backend.operations.worker import (
    ClaimedWork,
    ExecutionControl,
    ExecutorAcknowledgment,
    StartupDisposition,
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


@pytest.mark.serial
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


def _operation_poll_handler(
    manifest_digest: str,
    *,
    operation_id_override: str | None = None,
    expected_commit_id: str = EXPECTED_COMMIT_ID,
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


@pytest.mark.serial
def test_await_import_result_timeout_marks_manual_recovery(tmp_path: Path) -> None:
    def _running_forever_handler(request: httpx.Request) -> httpx.Response:
        if "/operations/" in request.url.path and request.method == "GET":
            operation_id = request.url.path.rsplit("/", 1)[-1]
            return httpx.Response(
                200,
                json={
                    "operation": {
                        "operation_id": operation_id,
                        "status": "RUNNING",
                        "error": None,
                        "result": None,
                    }
                },
                headers={"X-Request-ID": "req-operation"},
            )
        return default_repository_handler(request)

    transport = RecordingTransport(_running_forever_handler)
    harness = build_submit_worker_harness(
        tmp_path,
        repository_base_url="http://repository.test",
        transport=transport,
    )
    timeout_write = replace(
        cast(HttpRepositoryWriteClient, harness.submit_deps.repository_write),
        poll_deadline_seconds=0.2,
    )
    timeout_deps = replace(harness.submit_deps, repository_write=timeout_write)
    await_work, operation_id = _run_submit_to_await_claim(harness)
    worker_id, lease_token = _await_lease_identity(await_work)
    control, session = _lease_session(
        harness,
        worker_id=worker_id,
        lease_token=lease_token,
        operation_id=await_work.operation.operation_id,
        step_id=await_work.step.step_id,
    )
    handler = build_await_import_result_handler(timeout_deps)
    assert (
        handler(await_work.operation, await_work.step, control, session)
        is ExecutorAcknowledgment.PUBLISHED
    )
    with ControlDbUnitOfWork(harness.db_path, read_only=True) as unit_of_work:
        operation = unit_of_work.operations.get_operation(operation_id)
        await_step = unit_of_work.operations.get_step(
            submit_step_id(operation_id, SUBMIT_STEP_AWAIT)
        )
    assert operation.status is OperationStatus.MANUAL_RECOVERY_REQUIRED
    assert operation.diagnostic is not None
    assert operation.diagnostic.code == "R5.RECONCILE_TIMEOUT"
    assert await_step.status is StepStatus.MANUAL_RECOVERY_REQUIRED


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


def _run_await_binding_mismatch_case(
    tmp_path: Path,
    *,
    operation_id_override: str | None = None,
    expected_commit_id: str | None = None,
    completed_verification_policy: str | None = None,
    unknown_type_policy: str | None = None,
) -> tuple[OperationStatus, SubmitAttemptState]:
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
        expected_commit_id=expected_commit_id or EXPECTED_COMMIT_ID,
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
        return operation.status, attempt.state


def test_await_import_rejects_mismatched_repository_operation_id(tmp_path: Path) -> None:
    operation_status, attempt_state = _run_await_binding_mismatch_case(
        tmp_path,
        operation_id_override="00000000-0000-0000-0000-000000000099",
    )
    assert operation_status is OperationStatus.MANUAL_RECOVERY_REQUIRED
    assert attempt_state is SubmitAttemptState.EFFECT_PENDING


def test_await_import_rejects_mismatched_expected_commit_id(tmp_path: Path) -> None:
    operation_status, attempt_state = _run_await_binding_mismatch_case(
        tmp_path,
        expected_commit_id="commit-wrong",
    )
    assert operation_status is OperationStatus.MANUAL_RECOVERY_REQUIRED
    assert attempt_state is SubmitAttemptState.EFFECT_PENDING


def test_await_import_rejects_mismatched_verification_policy(tmp_path: Path) -> None:
    operation_status, attempt_state = _run_await_binding_mismatch_case(
        tmp_path,
        completed_verification_policy=VerificationPolicy.FULL_SCAN.value,
    )
    assert operation_status is OperationStatus.MANUAL_RECOVERY_REQUIRED
    assert attempt_state is SubmitAttemptState.EFFECT_PENDING


def test_await_import_rejects_mismatched_unknown_type_policy(tmp_path: Path) -> None:
    operation_status, attempt_state = _run_await_binding_mismatch_case(
        tmp_path,
        unknown_type_policy=UnknownTypePolicy.STRINGIFY.value,
    )
    assert operation_status is OperationStatus.MANUAL_RECOVERY_REQUIRED
    assert attempt_state is SubmitAttemptState.EFFECT_PENDING


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
        await_step = unit_of_work.operations.get_step(
            submit_step_id(operation_id, SUBMIT_STEP_AWAIT)
        )
        assert await_step.checkpoint_ref is not None
        envelope = load_checkpoint_envelope(harness.artifact_store, await_step.checkpoint_ref)
        evidence_ref = envelope.job_state.get("terminal_result_evidence_ref")
        assert type(evidence_ref) is dict
        assert not unit_of_work.protection.is_protected(await_step.checkpoint_ref.artifact_id)
        assert not unit_of_work.protection.is_protected(evidence_ref["artifact_id"])


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
