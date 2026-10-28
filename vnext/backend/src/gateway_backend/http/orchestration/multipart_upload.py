"""Multipart upload orchestration for AcceptUpload."""

from __future__ import annotations

import json
import shutil
from datetime import datetime

import anyio
from gateway_shared_kernel import DigestRef

from gateway_backend.application.submission.ports import SubmitControlUnitOfWorkFactory
from gateway_backend.application.workspace.contracts import AcceptUploadCommand
from gateway_backend.application.workspace.services import accept_upload
from gateway_backend.artifacts.bounded_store import BoundedArtifactStorePort
from gateway_backend.artifacts.store import ManifestVerificationError
from gateway_backend.artifacts.types import ArtifactRef
from gateway_backend.domain.workspace.models import (
    IdentityContext,
    InputCompleteness,
    SourceArtifactBinding,
    SourceArtifactRole,
)
from gateway_backend.domain.workspace.ports import ScopeResolutionPort, WorkspaceRepository
from gateway_backend.http.errors import ApiError
from gateway_backend.http.mappers import upload_revision_to_response
from gateway_backend.http.orchestration.multipart_stream import (
    ParsedMultipartUpload,
    iter_file_chunks,
)
from gateway_backend.http.orchestration.source_package_admission import (
    UploadLimitExceededError,
    UploadMediaUnsupportedError,
    assert_supported_source_media_type,
    validate_source_package_archive,
)
from gateway_backend.http.schemas.upload import ArtifactManifestPart, UploadManifestPart, UploadRevisionResponse
from gateway_backend.application.workspace.contracts import FIXED_UPLOAD_MAX_COMPRESSED_BYTES


async def accept_multipart_upload(
    *,
    context: IdentityContext,
    workspace_id: str,
    idempotency_key: str,
    parsed: ParsedMultipartUpload,
    scope_resolution: ScopeResolutionPort,
    workspace_repository: WorkspaceRepository,
    unit_of_work_factory: SubmitControlUnitOfWorkFactory,
    artifact_store: BoundedArtifactStorePort,
    now: datetime,
) -> UploadRevisionResponse:
    del workspace_repository
    try:
        return await anyio.to_thread.run_sync(
            lambda: _accept_staged_upload(
                context=context,
                workspace_id=workspace_id,
                idempotency_key=idempotency_key,
                parsed=parsed,
                scope_resolution=scope_resolution,
                unit_of_work_factory=unit_of_work_factory,
                artifact_store=artifact_store,
                now=now,
            ),
            abandon_on_cancel=False,
        )
    finally:
        shutil.rmtree(parsed.staging_dir, ignore_errors=True)


def _accept_staged_upload(
    *,
    context: IdentityContext,
    workspace_id: str,
    idempotency_key: str,
    parsed: ParsedMultipartUpload,
    scope_resolution: ScopeResolutionPort,
    unit_of_work_factory: SubmitControlUnitOfWorkFactory,
    artifact_store: BoundedArtifactStorePort,
    now: datetime,
) -> UploadRevisionResponse:
    try:
        manifest_payload = json.loads(parsed.manifest_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ApiError(
            code="REQUEST_VALIDATION_FAILED",
            message="manifest must be valid JSON",
            status_code=422,
        ) from exc
    try:
        manifest = UploadManifestPart.model_validate(manifest_payload)
    except Exception as exc:
        raise ApiError(
            code="REQUEST_VALIDATION_FAILED",
            message="manifest validation failed",
            status_code=422,
            details={"reason": str(exc)},
        ) from exc

    declared_parts: dict[str, tuple[SourceArtifactRole, ArtifactManifestPart]] = {}
    if manifest.input_completeness == "FULL":
        if manifest.artifacts.INITIAL is None:
            raise ApiError(
                code="UPLOAD_CLOSURE_INVALID",
                message="FULL upload requires INITIAL artifact",
                status_code=422,
            )
        declared_parts[manifest.artifacts.INITIAL.part_name] = (
            SourceArtifactRole.INITIAL,
            manifest.artifacts.INITIAL,
        )
    elif manifest.artifacts.INITIAL is not None:
        raise ApiError(
            code="UPLOAD_CLOSURE_INVALID",
            message="MODIFIED_ONLY upload must not include INITIAL artifact",
            status_code=422,
        )
    declared_parts[manifest.artifacts.MODIFIED.part_name] = (
        SourceArtifactRole.MODIFIED,
        manifest.artifacts.MODIFIED,
    )

    if set(parsed.file_parts) != set(declared_parts):
        raise ApiError(
            code="REQUEST_VALIDATION_FAILED",
            message="file parts must exactly match manifest part_name mapping",
            status_code=422,
            details={
                "declared": sorted(declared_parts),
                "received": sorted(parsed.file_parts),
            },
        )

    source_artifacts: dict[SourceArtifactRole, SourceArtifactBinding] = {}
    source_refs: list[ArtifactRef] = []
    for part_name, (role, declared) in declared_parts.items():
        assert_supported_source_media_type(declared.media_type)
        if declared.size_bytes > FIXED_UPLOAD_MAX_COMPRESSED_BYTES:
            raise UploadLimitExceededError("compressed source package exceeds budget")
        staged = parsed.file_parts[part_name]
        if staged.size_bytes != declared.size_bytes:
            raise ApiError(
                code="REQUEST_VALIDATION_FAILED",
                message="part size mismatch",
                status_code=422,
            )
        try:
            ref = artifact_store.put_stream(
                "source-package",
                iter_file_chunks(staged.path),
                declared_size=declared.size_bytes,
                declared_raw_sha256=DigestRef(declared.raw_sha256),
                media_type=declared.media_type,
            )
        except ManifestVerificationError as exc:
            raise _map_store_error(exc) from exc
        except ValueError as exc:
            raise _map_store_error(exc) from exc
        with staged.path.open("rb") as handle:
            validate_source_package_archive(handle, compressed_bytes=staged.size_bytes)
        source_refs.append(ref)
        source_artifacts[role] = SourceArtifactBinding(
            artifact_id=ref.artifact_id,
            media_type=ref.media_type,
            size_bytes=ref.size_bytes,
            raw_sha256=ref.raw_sha256.value,
        )

    completeness = InputCompleteness(manifest.input_completeness)
    command = AcceptUploadCommand(
        context=context,
        workspace_id=workspace_id,
        expected_workspace_version=manifest.expected_workspace_version,
        idempotency_key=idempotency_key,
        input_completeness=completeness,
        source_artifacts=source_artifacts,
        now=now,
    )
    with unit_of_work_factory() as unit_of_work:
        result = accept_upload(
            command=command,
            scope_resolution=scope_resolution,
            repository=unit_of_work.workspace,
            operations=unit_of_work.operations,
            protection=unit_of_work,
        )
        if not result.replay and source_refs:
            unit_of_work.set_artifact_protection(
                tuple(source_refs),
                owner_kind="upload-revision",
                owner_id=result.revision.upload_revision_id,
                intent="active-source",
            )
    return upload_revision_to_response(
        result.revision,
        optimistic_version=result.workspace.optimistic_version,
    )


def _map_store_error(exc: Exception) -> Exception:
    message = str(exc)
    lowered = message.lower()
    if "media" in lowered or "archive" in lowered:
        return UploadMediaUnsupportedError(message)
    if "declared_raw_sha256" in lowered or "shorter than declared_size" in lowered:
        return ApiError(
            code="REQUEST_VALIDATION_FAILED",
            message="uploaded bytes do not match the declared digest or size",
            status_code=422,
        )
    return UploadLimitExceededError(message)
