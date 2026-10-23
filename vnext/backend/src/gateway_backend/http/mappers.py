"""DTO mappers for workspace HTTP responses."""

from __future__ import annotations

from gateway_backend.application.workspace.contracts import PreviewReadState
from gateway_backend.domain.workspace.models import (
    SourceArtifactBinding,
    SourceArtifactRole,
    UploadRevision,
    Workspace,
)
from gateway_backend.http.schemas.operation import (
    OperationDiagnosticDetailResponse,
    OperationDiagnosticResponse,
    OperationResponse,
)
from gateway_backend.http.schemas.preview import (
    PreviewArtifactRefResponse,
    PreviewIdentityPairResponse,
    PreviewResultResponse,
)
from gateway_backend.http.schemas.upload import SourceArtifactResponse, UploadRevisionResponse
from gateway_backend.http.schemas.workspace import WorkspaceResponse
from gateway_backend.operations.contracts import OperationRecord


def workspace_to_response(workspace: Workspace) -> WorkspaceResponse:
    return WorkspaceResponse(
        workspace_id=workspace.workspace_id,
        gateway_device_external_key=workspace.gateway_device_external_key,
        business_project_id=workspace.business_project_id,
        state=workspace.state.value,
        generation=workspace.generation,
        current_upload_revision_id=workspace.current_upload_revision_id,
        current_preview_result_id=workspace.current_preview_result_id,
        optimistic_version=workspace.optimistic_version,
        created_at=workspace.created_at,
        updated_at=workspace.updated_at,
    )


def upload_revision_to_response(
    revision: UploadRevision,
    *,
    optimistic_version: int,
) -> UploadRevisionResponse:
    source_artifacts = {
        role.value: SourceArtifactResponse(
            artifact_id=binding.artifact_id,
            media_type=binding.media_type,
            size_bytes=binding.size_bytes,
            raw_sha256=binding.raw_sha256,
        )
        for role, binding in sorted(revision.source_artifacts.items(), key=lambda item: item[0].value)
    }
    return UploadRevisionResponse(
        upload_revision_id=revision.upload_revision_id,
        workspace_id=revision.workspace_id,
        generation=revision.generation,
        input_completeness=revision.input_completeness.value,
        source_artifacts=source_artifacts,
        optimistic_version=optimistic_version,
        created_at=revision.created_at,
    )


def preview_result_to_response(state: PreviewReadState) -> PreviewResultResponse:
    result = state.result
    return PreviewResultResponse(
        preview_result_id=result.preview_result_id,
        workspace_id=result.workspace_id,
        upload_revision_id=result.upload_revision_id,
        generation=result.generation,
        operation_id=result.operation_id,
        business_baseline_node_id=result.business_baseline_node_id,
        business_baseline_commit_id=result.business_baseline_commit_id,
        derived_stale=state.derived_stale,
        bundle_digest=result.digests.bundle_digest,
        identity_assessment_set_digest=result.identity_assessment_set_digest.value,
        identity_pairs=[
            PreviewIdentityPairResponse(
                pair_id=item.pair_id,
                applicability=item.applicability.value,
                status=item.status.value,
                mode=item.mode.value,
                assessment_ref=(
                    None
                    if item.assessment_ref is None
                    else PreviewArtifactRefResponse(
                        artifact_id=item.assessment_ref.artifact_id,
                        media_type=item.assessment_ref.media_type,
                        size_bytes=item.assessment_ref.size_bytes,
                        raw_sha256=item.assessment_ref.raw_sha256.value,
                    )
                ),
                assessment_digest=(
                    None if item.assessment_digest is None else item.assessment_digest.value
                ),
            )
            for item in result.identity_pairs
        ],
        created_at=result.created_at,
    )


def operation_to_response(operation: OperationRecord) -> OperationResponse:
    diagnostic = None
    if operation.diagnostic is not None:
        diagnostic = OperationDiagnosticResponse(
            code=operation.diagnostic.code,
            message=operation.diagnostic.message,
            details=(
                None
                if operation.diagnostic.details is None
                else [
                    OperationDiagnosticDetailResponse(
                        code=item.code,
                        side=item.side.value,
                        table_name=item.table_name,
                        column_name=item.column_name,
                    )
                    for item in operation.diagnostic.details
                ]
            ),
            omitted_count=operation.diagnostic.omitted_count,
        )
    return OperationResponse(
        operation_id=operation.operation_id,
        job_kind=operation.job_kind,
        status=operation.status.value,
        optimistic_version=operation.optimistic_version,
        created_at=operation.created_at,
        started_at=None,
        completed_at=operation.completed_at,
        diagnostic=diagnostic,
    )


def binding_to_response(binding: SourceArtifactBinding) -> SourceArtifactResponse:
    return SourceArtifactResponse(
        artifact_id=binding.artifact_id,
        media_type=binding.media_type,
        size_bytes=binding.size_bytes,
        raw_sha256=binding.raw_sha256,
    )


def role_from_key(key: str) -> SourceArtifactRole:
    return SourceArtifactRole(key)
