"""Multipart upload orchestration for AcceptUpload."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime

from starlette.datastructures import UploadFile
from gateway_shared_kernel import raw_blob_digest

from gateway_backend.application.workspace.contracts import AcceptUploadCommand
from gateway_backend.application.workspace.services import accept_upload
from gateway_backend.domain.workspace.models import (
    IdentityContext,
    InputCompleteness,
    SourceArtifactBinding,
    SourceArtifactRole,
)
from gateway_backend.domain.workspace.ports import ScopeResolutionPort, WorkspaceRepository
from gateway_backend.http.errors import ApiError
from gateway_backend.http.mappers import upload_revision_to_response
from gateway_backend.http.schemas.upload import ArtifactManifestPart, UploadManifestPart, UploadRevisionResponse
from gateway_backend.artifacts.bounded_store import BoundedArtifactStorePort


class UploadLimitExceededError(Exception):
    """Raised when upload exceeds bounded budgets."""


class UploadMediaUnsupportedError(Exception):
    """Raised when upload media type or archive format is unsupported."""


async def accept_multipart_upload(
    *,
    context: IdentityContext,
    workspace_id: str,
    idempotency_key: str,
    manifest_part: UploadFile,
    file_parts: Mapping[str, UploadFile],
    scope_resolution: ScopeResolutionPort,
    workspace_repository: WorkspaceRepository,
    artifact_store: BoundedArtifactStorePort,
    now: datetime,
) -> UploadRevisionResponse:
    manifest_bytes = await manifest_part.read()
    try:
        manifest_payload = json.loads(manifest_bytes.decode("utf-8"))
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

    if set(file_parts) != set(declared_parts):
        raise ApiError(
            code="REQUEST_VALIDATION_FAILED",
            message="file parts must exactly match manifest part_name mapping",
            status_code=422,
            details={
                "declared": sorted(declared_parts),
                "received": sorted(file_parts),
            },
        )

    source_artifacts: dict[SourceArtifactRole, SourceArtifactBinding] = {}
    for part_name, (role, declared) in declared_parts.items():
        upload_file = file_parts[part_name]
        raw_bytes = await upload_file.read()
        if len(raw_bytes) != declared.size_bytes:
            raise ApiError(
                code="REQUEST_VALIDATION_FAILED",
                message=f"part {part_name!r} size mismatch",
                status_code=422,
            )
        digest = raw_blob_digest(raw_bytes)
        if digest.value != declared.raw_sha256:
            raise ApiError(
                code="REQUEST_VALIDATION_FAILED",
                message=f"part {part_name!r} digest mismatch",
                status_code=422,
            )
        try:
            ref = artifact_store.put_stream(
                "source-package",
                [raw_bytes],
                declared_size=declared.size_bytes,
                declared_raw_sha256=digest,
                media_type=declared.media_type,
            )
        except ValueError as exc:
            message = str(exc)
            if "media" in message.lower() or "archive" in message.lower():
                raise UploadMediaUnsupportedError(message) from exc
            raise UploadLimitExceededError(message) from exc
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
    result = accept_upload(
        command=command,
        scope_resolution=scope_resolution,
        repository=workspace_repository,
    )
    return upload_revision_to_response(
        result.revision,
        optimistic_version=result.workspace.optimistic_version,
    )
