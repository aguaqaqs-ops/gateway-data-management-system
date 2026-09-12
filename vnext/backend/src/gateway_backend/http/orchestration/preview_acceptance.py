"""Preview job payload and acceptance orchestration."""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime

from gateway_shared_kernel.jcs import canonicalize_json_value

from gateway_backend.application.job_definitions import JobDefinitionLookupError, JobDefinitionRegistry
from gateway_backend.application.workspace.contracts import (
    StartPreviewCommand,
    compute_preview_request_fingerprint,
)
from gateway_backend.application.workspace.preview import validate_start_preview_binding
from gateway_shared_kernel import DigestRef

from gateway_backend.artifacts.bounded_store import BoundedArtifactStorePort
from gateway_backend.artifacts.types import ArtifactRef
from gateway_backend.domain.workspace.models import (
    IdentityContext,
    PreviewAcceptanceRecord,
    UploadRevision,
)
from gateway_backend.domain.workspace.ports import ScopeResolutionPort, WorkspaceRepository
from gateway_backend.http.errors import ApiError
from gateway_backend.http.schemas.preview import OperationAcceptedResponse
from gateway_backend.infrastructure.control_db.database import ControlDbUnitOfWork
from gateway_backend.operations import (
    OPERATION_RUNTIME_CONTRACT_VERSION,
    BusinessReference,
    JobStepKey,
    OperationRecord,
    OperationStatus,
    StepRecord,
    StepStatus,
)

PREVIEW_JOB_KIND = "backend-vnext/preview"
PREVIEW_JOB_CONTRACT_VERSION = "backend-vnext/preview/v1"
PREVIEW_STEP_MATERIALIZE = "materialize_inputs"


@dataclass(frozen=True, slots=True)
class PreviewAcceptanceResult:
    response: OperationAcceptedResponse
    replay: bool


def assert_preview_job_registered(registry: JobDefinitionRegistry) -> None:
    key = JobStepKey(job_kind=PREVIEW_JOB_KIND, step_name=PREVIEW_STEP_MATERIALIZE)
    try:
        registry.resolve_runnable(key, PREVIEW_JOB_CONTRACT_VERSION)
    except JobDefinitionLookupError as exc:
        raise ApiError(
            code="SERVICE_NOT_READY",
            message="preview job definition is not registered",
            status_code=503,
        ) from exc


def build_preview_job_payload(
    *,
    workspace_id: str,
    upload_revision: UploadRevision,
    repository_id: str,
    business_baseline_node_id: str,
    business_baseline_commit_id: str,
    baseline_head_version: int,
    idempotency_key: str,
    options: Mapping[str, object] | None = None,
) -> bytes:
    source_artifacts: dict[str, dict[str, object]] = {}
    source_digests: dict[str, str] = {}
    for role, binding in sorted(upload_revision.source_artifacts.items(), key=lambda item: item[0].value):
        source_artifacts[role.value] = {
            "artifact_id": binding.artifact_id,
            "media_type": binding.media_type,
            "size_bytes": binding.size_bytes,
            "raw_sha256": binding.raw_sha256,
        }
        source_digests[role.value] = binding.raw_sha256
    payload = {
        "workspace_id": workspace_id,
        "upload_revision_id": upload_revision.upload_revision_id,
        "generation": upload_revision.generation,
        "repository_id": repository_id,
        "business_baseline_node_id": business_baseline_node_id,
        "business_baseline_commit_id": business_baseline_commit_id,
        "baseline_head_version": baseline_head_version,
        "input_completeness": upload_revision.input_completeness.value,
        "source_artifacts": source_artifacts,
        "source_digests": source_digests,
        "input_digest": upload_revision.request_fingerprint,
        "ruleset_version": "v1",
        "capability_contract_versions": {},
        "provider_versions": {},
        "ready_closure_contract_version": "v1",
        "idempotency_identity": {
            "workspace_id": workspace_id,
            "idempotency_key": idempotency_key,
        },
        "options": dict(options or {}),
    }
    return canonicalize_json_value(payload)


def deterministic_operation_id(*, workspace_id: str, idempotency_key: str) -> str:
    digest = hashlib.sha256(f"{workspace_id}:{idempotency_key}".encode("utf-8")).hexdigest()[:24]
    return f"op-{digest}"


def accept_preview_operation(
    *,
    command: StartPreviewCommand,
    scope_resolution: ScopeResolutionPort,
    workspace_repository: WorkspaceRepository,
    unit_of_work_factory: Callable[[], ControlDbUnitOfWork],
    job_registry: JobDefinitionRegistry,
    artifact_store: BoundedArtifactStorePort,
    now: datetime,
    options: Mapping[str, object] | None = None,
) -> PreviewAcceptanceResult:
    del workspace_repository
    resolved_options = dict(options or {})
    assert_preview_job_registered(job_registry)
    with unit_of_work_factory() as unit_of_work:
        validation = validate_start_preview_binding(
            command=command,
            scope_resolution=scope_resolution,
            repository=unit_of_work.workspace,
        )
        if validation.replay and validation.prior_acceptance is not None:
            return PreviewAcceptanceResult(
                response=OperationAcceptedResponse(
                    operation_id=validation.prior_acceptance.operation_id,
                    workspace_id=command.workspace_id,
                    upload_revision_id=command.upload_revision_id,
                    generation=command.generation,
                    status="QUEUED",
                ),
                replay=True,
            )
        upload_revision = validation.upload_revision
        source_refs = _source_artifact_refs(upload_revision)

    for ref, binding in zip(
        source_refs,
        (
            upload_revision.source_artifacts[role]
            for role in sorted(upload_revision.source_artifacts, key=lambda item: item.value)
        ),
        strict=True,
    ):
        verified = artifact_store.verify_readable(
            ref,
            expected_size=binding.size_bytes,
            expected_raw_sha256=DigestRef(binding.raw_sha256),
        )
        if not verified.verified:
            raise ApiError(
                code="DEPENDENCY_UNAVAILABLE",
                message="source artifact is not readable",
                status_code=503,
            )

    with unit_of_work_factory() as unit_of_work:
        validation = validate_start_preview_binding(
            command=command,
            scope_resolution=scope_resolution,
            repository=unit_of_work.workspace,
        )
        if validation.replay and validation.prior_acceptance is not None:
            return PreviewAcceptanceResult(
                response=OperationAcceptedResponse(
                    operation_id=validation.prior_acceptance.operation_id,
                    workspace_id=command.workspace_id,
                    upload_revision_id=command.upload_revision_id,
                    generation=command.generation,
                    status="QUEUED",
                ),
                replay=True,
            )

        operation_id = deterministic_operation_id(
            workspace_id=command.workspace_id,
            idempotency_key=command.idempotency_key,
        )
        step_id = f"{operation_id}-step-1"
        job_payload = build_preview_job_payload(
            workspace_id=command.workspace_id,
            upload_revision=validation.upload_revision,
            repository_id=validation.workspace.repository_id,
            business_baseline_node_id=validation.baseline_head.business_baseline_node_id,
            business_baseline_commit_id=validation.baseline_head.business_baseline_commit_id,
            baseline_head_version=validation.baseline_head.baseline_head_version,
            idempotency_key=command.idempotency_key,
            options=resolved_options,
        )
        source_refs = _source_artifact_refs(validation.upload_revision)
        operation = OperationRecord(
            contract_version=OPERATION_RUNTIME_CONTRACT_VERSION,
            operation_id=operation_id,
            job_kind=PREVIEW_JOB_KIND,
            job_contract_version=PREVIEW_JOB_CONTRACT_VERSION,
            job_payload=job_payload,
            job_payload_ref=None,
            business_refs=(
                BusinessReference(kind="workspace", value=command.workspace_id),
                BusinessReference(kind="upload_revision", value=command.upload_revision_id),
            ),
            artifact_refs=source_refs,
            repository_operation_id=None,
            checkpoint_ref=None,
            ready_closure_ref=None,
            status=OperationStatus.QUEUED,
            diagnostic=None,
            cancel_requested=False,
            created_at=now,
            updated_at=now,
            completed_at=None,
            optimistic_version=0,
        )
        step = StepRecord(
            contract_version=OPERATION_RUNTIME_CONTRACT_VERSION,
            step_id=step_id,
            operation_id=operation_id,
            step_name=PREVIEW_STEP_MATERIALIZE,
            status=StepStatus.PENDING,
            attempt_count=0,
            diagnostic=None,
            cancel_requested=False,
            retry_not_before=None,
            worker_id=None,
            lease_token=None,
            lease_expires_at=None,
            checkpoint_ref=None,
            prior_output_refs=(),
            created_at=now,
            updated_at=now,
            started_at=None,
            completed_at=None,
            optimistic_version=0,
        )
        unit_of_work.operations.insert_operation_with_initial_step(operation, step)
        unit_of_work.workspace.save_preview_acceptance(
            PreviewAcceptanceRecord(
                workspace_id=command.workspace_id,
                idempotency_key=command.idempotency_key,
                request_fingerprint=command.request_fingerprint,
                operation_id=operation_id,
                upload_revision_id=command.upload_revision_id,
                generation=command.generation,
                business_baseline_node_id=validation.baseline_head.business_baseline_node_id,
                baseline_head_version=validation.baseline_head.baseline_head_version,
            )
        )
        if source_refs:
            unit_of_work.set_artifact_protection(
                source_refs,
                owner_kind="preview-operation",
                owner_id=operation_id,
                intent="active-operation",
            )

    return PreviewAcceptanceResult(
        response=OperationAcceptedResponse(
            operation_id=operation_id,
            workspace_id=command.workspace_id,
            upload_revision_id=command.upload_revision_id,
            generation=command.generation,
            status="QUEUED",
        ),
        replay=False,
    )


def _source_artifact_refs(upload_revision: UploadRevision) -> tuple[ArtifactRef, ...]:
    refs: list[ArtifactRef] = []
    for role in sorted(upload_revision.source_artifacts, key=lambda item: item.value):
        binding = upload_revision.source_artifacts[role]
        refs.append(
            ArtifactRef(
                artifact_id=binding.artifact_id,
                media_type=binding.media_type,
                size_bytes=binding.size_bytes,
                raw_sha256=DigestRef(binding.raw_sha256),
            )
        )
    return tuple(refs)


def build_start_preview_command(
    *,
    context: IdentityContext,
    workspace_id: str,
    expected_workspace_version: int,
    upload_revision_id: str,
    generation: int,
    expected_baseline_node_id: str,
    expected_baseline_head_version: int,
    idempotency_key: str,
    request_fingerprint_seed: Mapping[str, object],
) -> StartPreviewCommand:
    fingerprint = compute_preview_request_fingerprint(
        workspace_id=workspace_id,
        expected_workspace_version=expected_workspace_version,
        upload_revision_id=upload_revision_id,
        generation=generation,
        expected_baseline_node_id=expected_baseline_node_id,
        expected_baseline_head_version=expected_baseline_head_version,
        request_fingerprint_seed=request_fingerprint_seed,
    )
    return StartPreviewCommand(
        context=context,
        workspace_id=workspace_id,
        expected_workspace_version=expected_workspace_version,
        upload_revision_id=upload_revision_id,
        generation=generation,
        expected_baseline_node_id=expected_baseline_node_id,
        expected_baseline_head_version=expected_baseline_head_version,
        idempotency_key=idempotency_key,
        request_fingerprint=fingerprint,
    )
