"""Application boundary for versioned import submission and operation polling."""

from __future__ import annotations

import logging
from uuid import UUID

from pydantic import ValidationError

from gateway_repository_contracts import (
    GetOperationResponse,
    ImportRequestHeaders,
    SubmitVersionedImportRequest,
    SubmitVersionedImportResponse,
    VersionedOperation,
)
from gateway_repository_service.capacity import (
    CapacityAdmissionError,
    assert_durable_root_writable,
    assert_import_disk_admission,
)
from gateway_repository_service.create_repository.visibility import is_repository_visible
from gateway_repository_service.http.errors import ServiceError
from gateway_repository_service.mutation_store import IdempotencyKeyHash
from gateway_repository_service.runtime import ServiceRuntime
from gateway_repository_service.upload_artifact.visibility import is_artifact_visible
from gateway_repository_service.versioned_import.models import (
    ImportArtifactBindingRejected,
    ImportFingerprintConflict,
    ImportManualBarrierRequired,
    ImportOperationStoreError,
    ImportQueueFull,
    ImportRequestBinding,
    StoredImportOperation,
    versioned_import_fingerprint_v1,
)

_LOGGER = logging.getLogger(__name__)


class ImportSubmissionService:
    def __init__(self, runtime: ServiceRuntime) -> None:
        self._runtime = runtime
        self._settings = runtime.settings
        self._layout = runtime.layout
        self._mutation_store = runtime.mutation_store
        self._import_store = runtime.import_store
        self._worker_pool = runtime.import_worker_pool

    def submit(
        self,
        path_repository_id: UUID,
        headers: ImportRequestHeaders,
        body: SubmitVersionedImportRequest,
        *,
        request_id: str | None,
    ) -> SubmitVersionedImportResponse:
        if body.repository_id != path_repository_id:
            raise ServiceError(
                code="REQUEST_VALIDATION_FAILED",
                message="path repository_id does not match request body",
                status_code=422,
            )
        if body.target_ref != "main":
            raise ServiceError(
                code="REQUEST_VALIDATION_FAILED",
                message="target_ref must be main",
                status_code=422,
            )

        key_hash = IdempotencyKeyHash.from_raw_key(headers.idempotency_key)
        binding = _binding_from_request(body)
        fingerprint = versioned_import_fingerprint_v1(binding=binding, key_hash=key_hash)

        try:
            existing = self._import_store.lookup_by_key(path_repository_id, key_hash)
        except Exception as exc:
            raise _service_not_ready("control database lookup failed") from exc

        if existing is not None:
            stored_fingerprint = self._import_store.fingerprint_for_key(path_repository_id, key_hash)
            if stored_fingerprint != fingerprint:
                _log_submission_event(
                    "conflicted",
                    request_id=request_id,
                    repository_id=path_repository_id,
                    operation_id=existing.operation_id,
                    artifact_id=existing.artifact_id,
                    status=existing.status.value,
                    code="IDEMPOTENCY_CONFLICT",
                )
                raise ServiceError(
                    code="IDEMPOTENCY_CONFLICT",
                    message="idempotency key was reused with a different request",
                    status_code=409,
                )
            _log_submission_event(
                "replayed",
                request_id=request_id,
                repository_id=path_repository_id,
                operation_id=existing.operation_id,
                artifact_id=existing.artifact_id,
                status=existing.status.value,
            )
            self._worker_pool.notify()
            return SubmitVersionedImportResponse(operation_id=existing.operation_id)

        self._preflight_new_effect(path_repository_id, binding)
        try:
            result = self._import_store.admit_new_import(
                binding,
                key_hash=key_hash,
                fingerprint=fingerprint,
                max_queued_imports=self._settings.max_queued_imports,
            )
        except ImportFingerprintConflict:
            existing = self._import_store.lookup_by_key(path_repository_id, key_hash)
            if existing is None:
                raise _service_not_ready("control database lookup failed after conflict") from None
            stored_fingerprint = self._import_store.fingerprint_for_key(path_repository_id, key_hash)
            if stored_fingerprint != fingerprint:
                raise ServiceError(
                    code="IDEMPOTENCY_CONFLICT",
                    message="idempotency key was reused with a different request",
                    status_code=409,
                )
            self._worker_pool.notify()
            return SubmitVersionedImportResponse(operation_id=existing.operation_id)
        except ImportManualBarrierRequired as exc:
            _log_submission_event(
                "admission-denied",
                request_id=request_id,
                repository_id=path_repository_id,
                artifact_id=binding.artifact_ref.artifact_id,
                code="MANUAL_RECOVERY_REQUIRED",
            )
            raise ServiceError(
                code="MANUAL_RECOVERY_REQUIRED",
                message="repository requires manual recovery before new imports",
                status_code=409,
            ) from exc
        except ImportQueueFull as exc:
            _log_submission_event(
                "admission-denied",
                request_id=request_id,
                repository_id=path_repository_id,
                artifact_id=binding.artifact_ref.artifact_id,
                code="IMPORT_QUEUE_FULL",
            )
            raise ServiceError(
                code="IMPORT_QUEUE_FULL",
                message="import queue is full",
                status_code=429,
            ) from exc
        except ImportArtifactBindingRejected as exc:
            raise ServiceError(
                code="ARTIFACT_NOT_FOUND",
                message="artifact was not found",
                status_code=404,
            ) from exc
        except ImportOperationStoreError as exc:
            raise _service_not_ready("control database admission failed") from exc
        except Exception as exc:
            raise _service_not_ready("control database admission failed") from exc

        if not result.is_new:
            self._worker_pool.notify()
            return SubmitVersionedImportResponse(operation_id=result.operation_id)

        _log_submission_event(
            "accepted",
            request_id=request_id,
            repository_id=path_repository_id,
            operation_id=result.operation_id,
            artifact_id=binding.artifact_ref.artifact_id,
            status=result.operation.status.value,
            verification_policy=binding.verification_policy.value,
            unknown_type_policy=binding.unknown_type_policy.value,
            size_bytes=binding.artifact_ref.size_bytes,
        )
        self._worker_pool.notify()
        return SubmitVersionedImportResponse(operation_id=result.operation_id)

    def get_operation(self, repository_id: UUID, operation_id: UUID) -> GetOperationResponse:
        try:
            stored = self._import_store.get_operation(repository_id, operation_id)
        except Exception as exc:
            raise _service_not_ready("control database lookup failed") from exc
        if stored is None:
            raise ServiceError(
                code="OPERATION_NOT_FOUND",
                message="operation was not found",
                status_code=404,
            )
        try:
            operation = _to_versioned_operation(stored)
        except ValidationError as exc:
            raise ServiceError(
                code="INTERNAL_ERROR",
                message="internal server error",
                status_code=500,
            ) from exc
        return GetOperationResponse(operation=operation)

    def _preflight_new_effect(self, repository_id: UUID, binding: ImportRequestBinding) -> None:
        if not self._runtime.is_accepting_import_effects():
            _log_submission_event(
                "admission-denied",
                repository_id=repository_id,
                artifact_id=binding.artifact_ref.artifact_id,
                code="SERVICE_NOT_READY",
            )
            raise _service_not_ready("service is shutting down")

        if not self._runtime.root_lock.is_held():
            _log_submission_event(
                "admission-denied",
                repository_id=repository_id,
                artifact_id=binding.artifact_ref.artifact_id,
                code="SERVICE_NOT_READY",
            )
            raise _service_not_ready("root lock is not held")

        if not self._runtime._control_db_ready():
            _log_submission_event(
                "admission-denied",
                repository_id=repository_id,
                artifact_id=binding.artifact_ref.artifact_id,
                code="SERVICE_NOT_READY",
            )
            raise _service_not_ready("control database is unavailable")

        if not self._runtime._provider_ready():
            _log_submission_event(
                "admission-denied",
                repository_id=repository_id,
                artifact_id=binding.artifact_ref.artifact_id,
                code="SERVICE_NOT_READY",
            )
            raise _service_not_ready("provider is unavailable")

        if not is_repository_visible(self._mutation_store, self._layout, repository_id):
            raise ServiceError(
                code="REPOSITORY_NOT_FOUND",
                message="repository was not found",
                status_code=404,
            )

        if not self._artifact_acceptable(repository_id, binding):
            raise ServiceError(
                code="ARTIFACT_NOT_FOUND",
                message="artifact was not found",
                status_code=404,
            )

        try:
            assert_durable_root_writable(self._layout.service_state)
            assert_import_disk_admission(self._layout.root, self._settings)
        except CapacityAdmissionError as exc:
            _log_submission_event(
                "admission-denied",
                repository_id=repository_id,
                artifact_id=binding.artifact_ref.artifact_id,
                code="DISK_ADMISSION_DENIED",
            )
            raise ServiceError(
                code="DISK_ADMISSION_DENIED",
                message="disk admission denied",
                status_code=503,
            ) from exc

    def _artifact_acceptable(self, repository_id: UUID, binding: ImportRequestBinding) -> bool:
        lifecycle = self._mutation_store.get_artifact_lifecycle(binding.artifact_ref.artifact_id)
        if lifecycle is None:
            return False
        if lifecycle.repository_id != repository_id:
            return False
        if lifecycle.media_type != binding.artifact_ref.media_type:
            return False
        if lifecycle.size_bytes != binding.artifact_ref.size_bytes:
            return False
        if lifecycle.raw_sha256 != binding.artifact_ref.raw_sha256:
            return False
        if lifecycle.consumed_at is not None or lifecycle.consumed_by_operation_id is not None:
            return False
        if lifecycle.bytes_deleted_at is not None:
            return False
        return is_artifact_visible(
            self._mutation_store,
            self._layout,
            repository_id,
            binding.artifact_ref.artifact_id,
            size_bytes=binding.artifact_ref.size_bytes,
            raw_sha256=binding.artifact_ref.raw_sha256,
        )


def _binding_from_request(body: SubmitVersionedImportRequest) -> ImportRequestBinding:
    return ImportRequestBinding(
        repository_id=body.repository_id,
        artifact_ref=body.artifact_ref,
        target_ref=body.target_ref,
        expected_commit_id=body.expected_commit_id,
        verification_policy=body.verification_policy,
        unknown_type_policy=body.unknown_type_policy,
    )


def _to_versioned_operation(stored: StoredImportOperation) -> VersionedOperation:
    return VersionedOperation(
        operation_id=stored.operation_id,
        status=stored.status,
        result=stored.result,
        error=stored.error,
    )


def _service_not_ready(message: str) -> ServiceError:
    return ServiceError(
        code="SERVICE_NOT_READY",
        message=message,
        status_code=503,
    )


def _log_submission_event(
    event: str,
    *,
    request_id: str | None = None,
    repository_id: UUID | None = None,
    operation_id: UUID | None = None,
    artifact_id: UUID | None = None,
    status: str | None = None,
    code: str | None = None,
    verification_policy: str | None = None,
    unknown_type_policy: str | None = None,
    size_bytes: int | None = None,
) -> None:
    payload: dict[str, object] = {"event": f"import-submission-{event}"}
    if request_id is not None:
        payload["request_id"] = request_id
    if repository_id is not None:
        payload["repository_id"] = str(repository_id)
    if operation_id is not None:
        payload["operation_id"] = str(operation_id)
    if artifact_id is not None:
        payload["artifact_id"] = str(artifact_id)
    if status is not None:
        payload["status"] = status
    if code is not None:
        payload["code"] = code
    if verification_policy is not None:
        payload["verification_policy"] = verification_policy
    if unknown_type_policy is not None:
        payload["unknown_type_policy"] = unknown_type_policy
    if size_bytes is not None:
        payload["size_bytes"] = size_bytes
    _LOGGER.info("import submission %s", payload)
