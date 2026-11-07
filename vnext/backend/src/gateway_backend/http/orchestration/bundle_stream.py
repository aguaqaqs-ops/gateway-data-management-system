"""Bundle streaming orchestration."""

from __future__ import annotations

from gateway_backend.artifacts.bundle_download import PreparedBundleDownload
from gateway_backend.artifacts.store import ArtifactUnavailableError
from gateway_backend.artifacts.bundle_download import BundleIntegrityError
from gateway_backend.application.workspace.preview import read_preview_result
from gateway_backend.domain.workspace.models import IdentityContext
from gateway_backend.domain.workspace.ports import BaselineHeadReadPort, WorkspaceRepository
from gateway_backend.http.dependencies import BundleReaderPort
from gateway_backend.http.errors import ApiError


def stream_preview_bundle(
    *,
    context: IdentityContext,
    workspace_id: str,
    preview_result_id: str,
    workspace_repository: WorkspaceRepository,
    baseline_head_read: BaselineHeadReadPort,
    bundle_reader: BundleReaderPort,
) -> PreparedBundleDownload:
    state = read_preview_result(
        context=context,
        preview_result_id=preview_result_id,
        workspace_id=workspace_id,
        repository=workspace_repository,
        baseline_head_read=baseline_head_read,
    )
    try:
        return bundle_reader.prepare_bundle(state.result.bundle_artifact_id)
    except ArtifactUnavailableError:
        raise ApiError(
            code="RESOURCE_NOT_FOUND",
            message="bundle is not available",
            status_code=404,
        ) from None
    except BundleIntegrityError:
        raise ApiError(
            code="BUNDLE_INTEGRITY_FAILURE",
            message="bundle failed integrity verification",
            status_code=503,
        ) from None
